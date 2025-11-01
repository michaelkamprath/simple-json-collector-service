import importlib.util
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


class JsonCollectorAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_dir_ctx.cleanup)

        self.json_collector_service = json_collector_service

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
