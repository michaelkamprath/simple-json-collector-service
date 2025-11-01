import json
import os
from pathlib import Path

from tests.app_test_base import JsonCollectorAppTestCase


class JsonCollectorServiceTests(JsonCollectorAppTestCase):
    def test_health_check_endpoint_returns_success_message(self) -> None:
        status, _, body = self.invoke_app("GET", "/json-collector/health-check")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body.decode("utf-8"), "Everything is ay oh kay")

    def test_health_check_reports_missing_data_directory(self) -> None:
        missing_path = Path(self.data_dir_ctx.name) / "missing"
        self.json_collector_service.DATA_FILE_DIR = str(missing_path)

        status, _, body = self.invoke_app("GET", "/json-collector/health-check")
        self.assertTrue(status.startswith("500"))
        self.assertIn("DATA_FILE_DIR", body.decode("utf-8"))

    def test_post_request_persists_json_payload(self) -> None:
        payload = {"temperature": 21}
        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/test-dataset",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

        self.assertTrue(status.startswith("200"))
        self.assertIn("JSON data accepted for test-dataset", body.decode("utf-8"))

        dataset_path = Path(self.data_dir_ctx.name) / "testdataset.jsonl"
        self.assertTrue(dataset_path.exists())
        stored_lines = dataset_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(stored_lines), 1)
        record = json.loads(stored_lines[0])
        self.assertEqual(record["posted_data"], payload)
        self.assertEqual(record["request_url"], "http://localhost:8000/json-collector/test-dataset")

    def test_invalid_json_returns_bad_request(self) -> None:
        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/broken-feed",
            body="{not valid",
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(status.startswith("400"))
        self.assertIn("ERROR - improperly formatted JSON data", body.decode("utf-8"))

    def test_dataset_files_rotate_when_max_size_reached(self) -> None:
        os.environ["MAX_JSONL_FILE_SIZE"] = "1"

        self.invoke_app(
            "POST",
            "/json-collector/rotation-feed",
            body=json.dumps({"a": 1}),
            headers={"Content-Type": "application/json"},
        )
        dataset_path = Path(self.data_dir_ctx.name) / "rotationfeed.jsonl"
        initial_contents = dataset_path.read_text(encoding="utf-8").strip()
        self.assertTrue(initial_contents)

        self.invoke_app(
            "POST",
            "/json-collector/rotation-feed",
            body=json.dumps({"a": 2}),
            headers={"Content-Type": "application/json"},
        )

        rotated_path = Path(self.data_dir_ctx.name) / "rotationfeed.1.jsonl"
        self.assertTrue(rotated_path.exists())
        self.assertTrue(dataset_path.exists())

        rotated_lines = rotated_path.read_text(encoding="utf-8").strip().splitlines()
        new_lines = dataset_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(rotated_lines), 1)
        self.assertEqual(len(new_lines), 1)
        self.assertEqual(json.loads(rotated_lines[0])["posted_data"], {"a": 1})
        self.assertEqual(json.loads(new_lines[0])["posted_data"], {"a": 2})
