# This code is part of Qiskit.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Deterministic JSON conversion and hashing."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import numpy as np
from pydantic import BaseModel, JsonValue


class JsonConversionError(TypeError):
    """Raised when a value has no lossless, deterministic JSON representation."""


def _datetime_to_json(value: datetime) -> str:
    """Use UTC for aware values so equivalent instants have one representation."""
    if value.tzinfo is not None and value.utcoffset() is not None:
        value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="microseconds")


def to_json_safe(value: Any) -> JsonValue:
    """Convert supported Python/scientific values to a deterministic JSON value.

    Unknown model extension fields pass through this same boundary, so newly
    introduced NumPy, enum, and datetime values do not bypass serialization.
    Unsupported objects and non-finite floats fail instead of being stringified.
    """
    if isinstance(value, Enum):
        return to_json_safe(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonConversionError("non-finite floats are not valid canonical JSON")
        return value
    if isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.datetime64):
        if np.isnat(value).any():
            raise JsonConversionError("NumPy NaT is not valid canonical JSON")
        return to_json_safe(
            np.datetime_as_string(value, unit="ns", timezone="UTC").tolist()
        )
    if isinstance(value, np.ndarray):
        return to_json_safe(value.tolist())
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if value.dtype.itemsize > np.dtype(np.float64).itemsize:
            raise JsonConversionError(
                f"NumPy {value.dtype} cannot be represented losslessly as a JSON number"
            )
        return to_json_safe(float(value))
    if isinstance(value, np.str_):
        return str(value)
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            raise JsonConversionError("NumPy NaT is not valid canonical JSON")
        return str(np.datetime_as_string(value, unit="ns", timezone="UTC"))
    if isinstance(value, np.generic):
        raise JsonConversionError(
            f"NumPy {value.dtype} has no supported JSON representation"
        )
    if isinstance(value, datetime):
        return _datetime_to_json(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return to_json_safe(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        converted: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonConversionError(
                    f"JSON object keys must be strings, received {type(key).__name__}"
                )
            converted[key] = to_json_safe(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    raise JsonConversionError(
        f"unsupported JSON extension value of type {type(value).__module__}."
        f"{type(value).__qualname__}"
    )


def canonical_json(value: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for hashing and artifact storage."""
    safe_value = to_json_safe(value)
    return json.dumps(
        safe_value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_hash(value: Any) -> str:
    """Return the SHA-256 content identifier for canonical JSON."""
    return f"sha256:{hashlib.sha256(canonical_json(value)).hexdigest()}"
