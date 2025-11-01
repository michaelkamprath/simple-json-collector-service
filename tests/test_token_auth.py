import json
import os
from pathlib import Path

from flask import Flask

from tests.app_test_base import JsonCollectorAppTestCase
from token_auth import TokenAuthenticator, TokenConfigurationError, TokenValidationError


class TokenAuthIntegrationTests(JsonCollectorAppTestCase):
    def test_authorized_token_allows_post_and_redacts_header(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")

        os.environ["AUTHORIZED_TOKENS_FILE"] = str(tokens_file)
        os.environ["JSON_COLLECTOR_TOKEN_HEADER"] = "X-Custom-Token"
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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
        self.json_collector_service.token_authenticator = self.json_collector_service.configure_token_authentication()

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


class TokenAuthenticatorUnitTests(JsonCollectorAppTestCase):
    def test_configure_token_auth_raises_when_required_file_missing(self) -> None:
        missing_file = Path(self.data_dir_ctx.name) / "missing.json"
        os.environ["AUTHORIZED_TOKENS_FILE"] = str(missing_file)

        with self.assertRaises(TokenConfigurationError):
            self.json_collector_service.configure_token_authentication()

    def test_authenticated_username_reads_token_from_manifest(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")
        authenticator = TokenAuthenticator(
            file_path=str(tokens_file),
            header_name="X-Test-Token",
            require_file=True,
        )

        app = Flask("token-test")
        with app.test_request_context(headers={"X-Test-Token": "token-123"}):
            username = authenticator.authenticated_username()

        self.assertEqual(username, "alice")

    def test_authenticated_username_rejects_unknown_token(self) -> None:
        tokens_file = Path(self.data_dir_ctx.name) / "tokens.json"
        tokens_file.write_text(json.dumps({"alice": "token-123"}), encoding="utf-8")
        authenticator = TokenAuthenticator(
            file_path=str(tokens_file),
            header_name="X-Test-Token",
            require_file=True,
        )

        app = Flask("token-test")
        with app.test_request_context(headers={"X-Test-Token": "wrong"}):
            with self.assertRaisesRegex(TokenValidationError, "Provided token is not recognized"):
                authenticator.authenticated_username()
