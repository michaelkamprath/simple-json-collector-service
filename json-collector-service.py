import json
import os
import shutil
import time
from typing import Dict, Optional

import tornado.httpserver
import tornado.wsgi
import tornado.ioloop
from flask import Flask, abort, request, send_from_directory
from werkzeug.exceptions import BadRequest, NotFound

DATA_FILE_DIR = "/run/collector"
DATE_FILE_EXTENSION = "jsonl"
LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TOKEN_FILE_ENV_VAR = "AUTHORIZED_TOKENS_FILE"
TOKEN_HEADER_ENV_VAR = "JSON_COLLECTOR_TOKEN_HEADER"
DEFAULT_TOKEN_HEADER = "X-JSON-Collector-Token"
DEFAULT_TOKEN_FILE_PATH = f"{DATA_FILE_DIR}/authorized_tokens.json"

app = Flask(__name__)


class TokenConfigurationError(Exception):
    """Raised when the token configuration prevents the service from enforcing auth."""


class TokenValidationError(Exception):
    """Raised when a client request fails token authentication."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class TokenAuthenticator:
    def __init__(self, file_path: Optional[str], header_name: str, require_file: bool) -> None:
        self.file_path = file_path
        self.header_name = header_name
        self.require_file = require_file
        self.tokens_by_value: Dict[str, str] = {}
        self.enabled = False
        self._last_mtime: Optional[float] = None
        self._initialize()

    def _initialize(self) -> None:
        if not self.file_path:
            if self.require_file:
                raise TokenConfigurationError("Authorized tokens file path not provided")
            self.enabled = False
            return

        if not os.path.exists(self.file_path):
            if self.require_file:
                raise TokenConfigurationError(
                    f"Authorized tokens file not found at {self.file_path}"
                )
            self.enabled = False
            return

        self._reload_tokens(force=True)

    def _reload_tokens(self, force: bool = False) -> None:
        if not self.file_path:
            self.tokens_by_value = {}
            self.enabled = False
            self._last_mtime = None
            return

        if not os.path.exists(self.file_path):
            raise TokenConfigurationError(
                f"Authorized tokens file not found at {self.file_path}"
            )

        current_mtime = os.path.getmtime(self.file_path)
        if not force and self._last_mtime == current_mtime:
            return

        with open(self.file_path, "r", encoding="utf-8") as file_handle:
            try:
                token_mapping = json.load(file_handle)
            except json.JSONDecodeError as exc:
                raise TokenConfigurationError(
                    f"Authorized tokens file at {self.file_path} is not valid JSON"
                ) from exc

        if not isinstance(token_mapping, dict):
            raise TokenConfigurationError(
                "Authorized tokens file must contain a JSON object mapping usernames to tokens"
            )

        tokens_by_value: Dict[str, str] = {}
        for username, token in token_mapping.items():
            if not isinstance(username, str) or not isinstance(token, str):
                raise TokenConfigurationError(
                    "Authorized tokens file must map string usernames to string tokens"
                )

            username_clean = username.strip()
            token_clean = token.strip()
            if not username_clean or not token_clean:
                raise TokenConfigurationError(
                    "Authorized tokens file contains blank usernames or tokens"
                )

            tokens_by_value[token_clean] = username_clean

        if not tokens_by_value:
            raise TokenConfigurationError("Authorized tokens file is empty")

        self.tokens_by_value = tokens_by_value
        self.enabled = True
        self._last_mtime = current_mtime

    def is_enabled(self) -> bool:
        return self.enabled

    def authenticated_username(self) -> str:
        self._reload_tokens()

        header_value = request.headers.get(self.header_name)
        if header_value is None:
            raise TokenValidationError(
                f"Missing required token header '{self.header_name}'",
                status_code=401,
            )

        header_value = header_value.strip()
        if not header_value:
            raise TokenValidationError(
                f"Missing required token header '{self.header_name}'",
                status_code=401,
            )

        username = self.tokens_by_value.get(header_value)
        if username is None:
            raise TokenValidationError("Provided token is not recognized", status_code=403)

        return username


def configure_token_authentication() -> TokenAuthenticator:
    header_name = os.environ.get(TOKEN_HEADER_ENV_VAR, DEFAULT_TOKEN_HEADER)
    header_name = header_name.strip() if header_name else DEFAULT_TOKEN_HEADER
    if not header_name:
        header_name = DEFAULT_TOKEN_HEADER

    configured_path = os.environ.get(TOKEN_FILE_ENV_VAR)
    if configured_path:
        file_path = configured_path.strip()
        if not file_path:
            file_path = None
        require_file = True
    else:
        file_path = DEFAULT_TOKEN_FILE_PATH if os.path.exists(DEFAULT_TOKEN_FILE_PATH) else None
        require_file = False

    authenticator = TokenAuthenticator(file_path=file_path, header_name=header_name, require_file=require_file)
    return authenticator


token_authenticator = configure_token_authentication()


def clean_project_name(project: str) -> str:
    # since project is used a as file name, remove any symbols
    return "".join(filter(str.isalnum, project))


def log_request_event(time_str: str, status_code: int, payload, authenticated_user: Optional[str] = None):
    payload_str = "-"
    if payload not in (None, "", {}):
        payload_str = payload if isinstance(payload, str) else json.dumps(payload)
    remote_addr = request.remote_addr or "-"
    user_str = authenticated_user or "-"
    print(
        "{0} [{1}] {2} {3} {4} {5} {6}".format(
            remote_addr,
            time_str,
            request.method,
            request.url,
            status_code,
            payload_str,
            user_str,
        )
    )


@app.route("/json-collector/<project>", methods=["GET"])
def return_json_data(project: str):
    cleaned_project = clean_project_name(project)
    event_time_str = time.strftime(LOG_TIME_FORMAT, time.gmtime())
    authenticated_user: Optional[str] = None
    if token_authenticator.is_enabled():
        try:
            authenticated_user = token_authenticator.authenticated_username()
        except TokenValidationError as exc:
            log_request_event(event_time_str, exc.status_code, {"error": str(exc)}, None)
            return f"ERROR - {str(exc)}", exc.status_code
        except TokenConfigurationError as exc:
            log_request_event(event_time_str, 500, {"error": str(exc)}, None)
            return "ERROR - token authentication configuration failure", 500
    try:
        response = send_from_directory(
            DATA_FILE_DIR,
            "{0}.{1}".format(cleaned_project, DATE_FILE_EXTENSION),
            as_attachment=False,
        )
    except NotFound:
        log_request_event(event_time_str, 404, None, authenticated_user)
        abort(404, description="Unknown URL")

    log_request_event(event_time_str, response.status_code, None, authenticated_user)
    return response


@app.route("/json-collector/<project>", methods=["POST"])
def ingest_json_data(project: str):
    event_time = time.time()
    event_time_str = time.strftime(LOG_TIME_FORMAT, time.gmtime(event_time))
    cleaned_project = clean_project_name(project)

    authenticated_user: Optional[str] = None
    if token_authenticator.is_enabled():
        try:
            authenticated_user = token_authenticator.authenticated_username()
        except TokenValidationError as exc:
            log_request_event(event_time_str, exc.status_code, {"error": str(exc)}, None)
            return f"ERROR - {str(exc)}", exc.status_code
        except TokenConfigurationError as exc:
            log_request_event(event_time_str, 500, {"error": str(exc)}, None)
            return "ERROR - token authentication configuration failure", 500

    try:
        json_data = request.get_json(force=False, silent=False)
    except BadRequest:
        raw_body = (
            request.get_data(as_text=True).replace("\n", "").replace("\t", " ")
        )
        log_request_event(event_time_str, 400, raw_body, authenticated_user)
        return "ERROR - improperly formatted JSON data", 400

    if json_data is None:
        json_data = ""

    data_dict = {
        "timestamp": event_time,
        "client_ip": request.remote_addr,
        "request_headers": {},
        "request_url": request.url,
        "posted_data": json_data,
    }
    if authenticated_user:
        data_dict["authenticated_user"] = authenticated_user

    header_name_lower = token_authenticator.header_name.lower()
    for key, value in request.headers.items():
        if key.lower() == header_name_lower:
            data_dict["request_headers"][key] = "[REDACTED]"
        else:
            data_dict["request_headers"][key] = value

    max_size_env = os.environ.get("MAX_JSONL_FILE_SIZE")
    max_size = int(max_size_env) if max_size_env else 52428800

    filename = "{0}/{1}.{2}".format(
        DATA_FILE_DIR, cleaned_project, DATE_FILE_EXTENSION
    )
    rotate_file_if_needed(filename, max_size=max_size)

    with open(filename, "a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(data_dict) + "\n")

    log_request_event(event_time_str, 200, json_data, authenticated_user)
    return "JSON data accepted for {0}".format(project)


@app.route("/json-collector/health-check", methods=["GET"])
def return_health_check():
    log_request_event(time.strftime(LOG_TIME_FORMAT, time.gmtime()), 200, None)
    return "Everything is ay oh kay"


@app.errorhandler(404)
def error404(error):
    log_request_event(time.strftime(LOG_TIME_FORMAT, time.gmtime()), 404, None)
    return "Unknown URL", 404


def rotate_file_if_needed(filename: str, max_size: int):
    if os.path.exists(filename) and os.path.getsize(filename) >= max_size:
        backup_number = 1
        file_base, ext = os.path.splitext(filename)
        while os.path.exists(f"{file_base}.{backup_number}{ext}"):
            backup_number += 1

        shutil.move(filename, f"{file_base}.{backup_number}{ext}")


def main():
    container = tornado.wsgi.WSGIContainer(app)
    server = tornado.httpserver.HTTPServer(container)
    server.listen(port=8000)
    print("Started Simple JSON Collector Service listening on port 8000")
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
