import importlib.util
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple
from wsgiref.util import setup_testing_defaults


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "json-collector-service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("json_collector_service", MODULE_PATH)
json_collector_service = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(json_collector_service)


class JsonCollectorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_dir_ctx.cleanup)

        self.original_data_dir = json_collector_service.DATA_FILE_DIR
        json_collector_service.DATA_FILE_DIR = self.data_dir_ctx.name
        self.addCleanup(self._restore_data_dir)

        self.original_max_size = os.environ.get("MAX_JSONL_FILE_SIZE")
        self.addCleanup(self._restore_max_size)

        self.original_testing_flag = json_collector_service.app.testing
        json_collector_service.app.testing = True
        self.addCleanup(self._restore_testing_flag)

    def _restore_data_dir(self) -> None:
        json_collector_service.DATA_FILE_DIR = self.original_data_dir

    def _restore_max_size(self) -> None:
        if self.original_max_size is None:
            os.environ.pop("MAX_JSONL_FILE_SIZE", None)
        else:
            os.environ["MAX_JSONL_FILE_SIZE"] = self.original_max_size

    def _restore_testing_flag(self) -> None:
        json_collector_service.app.testing = self.original_testing_flag

    def invoke_app(
        self,
        method: str,
        path: str,
        body: bytes | str | None = None,
        headers: Dict[str, str] | None = None,
    ) -> Tuple[str, Dict[str, str], bytes]:
        environ: Dict[str, object] = {}
        setup_testing_defaults(environ)
        environ["REQUEST_METHOD"] = method
        environ["PATH_INFO"] = path
        environ["SERVER_NAME"] = "localhost"
        environ["SERVER_PORT"] = "8000"
        environ["HTTP_HOST"] = "localhost:8000"

        raw_body = b""
        if body is not None:
            raw_body = body if isinstance(body, bytes) else body.encode("utf-8")
        environ["wsgi.input"] = BytesIO(raw_body)
        environ["CONTENT_LENGTH"] = str(len(raw_body))

        if headers:
            for key, value in headers.items():
                if key.upper() == "CONTENT-TYPE":
                    environ["CONTENT_TYPE"] = value
                else:
                    header_key = f"HTTP_{key.upper().replace('-', '_')}"
                    environ[header_key] = value

        status_holder: Dict[str, str] = {}
        headers_holder: Dict[str, str] = {}

        def start_response(status: str, response_headers):
            status_holder["status"] = status
            headers_holder.update({key: val for key, val in response_headers})

        body_iterable = json_collector_service.app(environ, start_response)
        try:
            response_body = b"".join(body_iterable)
        finally:
            close_method = getattr(body_iterable, "close", None)
            if callable(close_method):
                close_method()

        return status_holder.get("status", "500 Internal Server Error"), headers_holder, response_body

    def test_health_check_endpoint_returns_success_message(self) -> None:
        status, _, body = self.invoke_app("GET", "/json-collector/health-check")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body.decode("utf-8"), "Everything is ay oh kay")

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


if __name__ == "__main__":
    unittest.main()
