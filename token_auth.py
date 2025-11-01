import json
import os
from typing import Dict, Optional

from flask import request


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
