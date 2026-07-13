# This code is part of Qiskit.
#
# (C) Copyright IBM 2025.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Security boundaries shared by Runtime core and MCP adapters."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"

_SECRET_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "id_token",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "token",
    }
)
_KEYED_SECRET = re.compile(
    r"(?i)(\b(?:access[_-]?token|api[_-]?key|authorization|client[_-]?secret|"
    r"credentials?|id[_-]?token|password|private[_-]?key|refresh[_-]?token|secret|token)"
    r"\b\s*[:=]\s*)"
    r"(?:Bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_KEY_SUFFIXES = (
    "_credential",
    "_credentials",
    "_key",
    "_password",
    "_secret",
    "_token",
)


def _is_secret_key(key: object) -> bool:
    """Return whether a mapping key denotes credential material."""
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SECRET_KEYS or normalized.endswith(_SECRET_KEY_SUFFIXES)


def redact_text(value: object) -> str:
    """Redact secret-like values from a human-readable value."""
    text = str(value)
    configured_token = os.getenv("QISKIT_IBM_TOKEN")
    if configured_token and configured_token.strip():
        text = text.replace(configured_token.strip(), REDACTED)
    text = _KEYED_SECRET.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    return _BEARER_SECRET.sub(f"Bearer {REDACTED}", text)


def redact_data(value: Any) -> Any:
    """Recursively redact secret-bearing fields and strings in public results."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_secret_key(key) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_data(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


class SecretRedactionFilter(logging.Filter):
    """Sanitize messages, arguments, and exception text before log emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            _, exc, traceback = record.exc_info
            if exc is not None:
                redacted = RuntimeError(redact_text(exc))
                record.exc_info = (RuntimeError, redacted, traceback)
        return True


def install_secret_redaction(target: logging.Logger) -> None:
    """Install redaction on a logger and its already configured handlers."""
    if not any(isinstance(item, SecretRedactionFilter) for item in target.filters):
        target.addFilter(SecretRedactionFilter())
    for handler in target.handlers:
        if not any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
            handler.addFilter(SecretRedactionFilter())
