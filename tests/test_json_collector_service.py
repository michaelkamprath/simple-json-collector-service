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

        self.original_tokens_file_env = os.environ.get("AUTHORIZED_TOKENS_FILE")
        self.original_token_header_env = os.environ.get("JSON_COLLECTOR_TOKEN_HEADER")
        self.addCleanup(self._restore_token_env)

        self.original_testing_flag = json_collector_service.app.testing
        json_collector_service.app.testing = True
        self.addCleanup(self._restore_testing_flag)

        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

    def _restore_data_dir(self) -> None:
        json_collector_service.DATA_FILE_DIR = self.original_data_dir

    def _restore_max_size(self) -> None:
        if self.original_max_size is None:
            os.environ.pop("MAX_JSONL_FILE_SIZE", None)
        else:
            os.environ["MAX_JSONL_FILE_SIZE"] = self.original_max_size

    def _restore_token_env(self) -> None:
        if self.original_tokens_file_env is None:
            os.environ.pop("AUTHORIZED_TOKENS_FILE", None)
        else:
            os.environ["AUTHORIZED_TOKENS_FILE"] = self.original_tokens_file_env

        if self.original_token_header_env is None:
            os.environ.pop("JSON_COLLECTOR_TOKEN_HEADER", None)
        else:
            os.environ["JSON_COLLECTOR_TOKEN_HEADER"] = self.original_token_header_env

        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

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

    def test_authorized_token_allows_post_and_redacts_header(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        os.environ["JSON_COLLECTOR_TOKEN_HEADER"] = "X-Custom-Token"
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        payload = {"temperature": 18}
        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/secure-feed",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "X-Custom-Token": "token-123",
            },
        )

        self.assertTrue(status.startswith("200"))
        self.assertIn("JSON data accepted for secure-feed", body.decode("utf-8"))

        dataset_path = Path(self.data_dir_ctx.name) / "securefeed.jsonl"
        stored_lines = dataset_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(stored_lines), 1)
        record = json.loads(stored_lines[0])
        self.assertEqual(record["posted_data"], payload)
        self.assertEqual(record.get("authenticated_user"), "alice")
        self.assertEqual(record["request_headers"].get("X-Custom-Token"), "[REDACTED]")

    def test_missing_token_header_returns_error_with_header_name(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        os.environ["JSON_COLLECTOR_TOKEN_HEADER"] = "X-JSON-Collector-Token"
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/secure-feed",
            body=json.dumps({"temperature": 21}),
            headers={"Content-Type": "application/json"},
        )

        self.assertTrue(status.startswith("401"))
        self.assertIn("Missing required token header 'X-JSON-Collector-Token'", body.decode("utf-8"))

    def test_invalid_token_is_rejected(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/secure-feed",
            body=json.dumps({"temperature": 21}),
            headers={
                "Content-Type": "application/json",
                "X-JSON-Collector-Token": "wrong-token",
            },
        )

        self.assertTrue(status.startswith("403"))
        self.assertIn("Provided token is not recognized", body.decode("utf-8"))

    def test_authorized_tokens_file_is_not_served_via_get(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "authorized_tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        status, _, _ = self.invoke_app(
            "GET",
            "/json-collector/authorized_tokens",
            headers={"X-JSON-Collector-Token": "token-123"},
        )

        self.assertTrue(status.startswith("404"))

    def test_get_requires_token_when_auth_enabled(self) -> None:
        dataset_path = Path(self.data_dir_ctx.name) / "securedataset.jsonl"
        dataset_path.write_text("{\"sample\": 1}\n", encoding="utf-8")

        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        status, _, _ = self.invoke_app(
            "GET",
            "/json-collector/secure-dataset",
        )
        self.assertTrue(status.startswith("401"))

        status, _, _ = self.invoke_app(
            "GET",
            "/json-collector/secure-dataset",
            headers={"X-JSON-Collector-Token": "wrong-token"},
        )
        self.assertTrue(status.startswith("403"))

        status, _, body = self.invoke_app(
            "GET",
            "/json-collector/secure-dataset",
            headers={"X-JSON-Collector-Token": "token-123"},
        )
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body.decode("utf-8"), "{\"sample\": 1}\n")

    def test_token_header_is_redacted_when_auth_disabled(self) -> None:
        os.environ.pop("AUTHORIZED_TOKENS_FILE", None)
        json_collector_service.token_authenticator = json_collector_service.configure_token_authentication()

        payload = {"temperature": 19}
        status, _, body = self.invoke_app(
            "POST",
            "/json-collector/no-auth-feed",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "X-JSON-Collector-Token": "should-not-leak",
            },
        )

        self.assertTrue(status.startswith("200"))
        self.assertIn("JSON data accepted for no-auth-feed", body.decode("utf-8"))

        dataset_path = Path(self.data_dir_ctx.name) / "noauthfeed.jsonl"
        record = json.loads(dataset_path.read_text(encoding="utf-8").strip())
        headers_lower = {k.lower(): v for k, v in record["request_headers"].items()}
        self.assertEqual(headers_lower.get("x-json-collector-token"), "[REDACTED]")
        self.assertNotIn("authenticated_user", record)


if __name__ == "__main__":
    unittest.main()
