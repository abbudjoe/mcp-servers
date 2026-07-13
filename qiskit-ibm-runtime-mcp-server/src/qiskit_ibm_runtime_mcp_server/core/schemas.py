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

"""Stable JSON Schema export for public Runtime research contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import PUBLIC_MODELS, SCHEMA_VERSION


def _schema_name(model_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", model_name).lower()


def schemas_directory() -> Path:
    """Return the checked-in schema directory for the current contract version."""
    return Path(__file__).with_name("json_schemas") / f"v{SCHEMA_VERSION}"


def generated_schemas() -> dict[str, dict[str, Any]]:
    """Generate deterministic draft 2020-12 schemas keyed by published filename."""
    result: dict[str, dict[str, Any]] = {}
    for model in PUBLIC_MODELS:
        name = _schema_name(model.__name__)
        # The validation schema is the authoritative wire contract. The custom
        # serializer only normalizes values inside that same object shape.
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            f"https://qiskit.org/schemas/runtime-research/v{SCHEMA_VERSION}/{name}.json"
        )
        schema["x-schema-version"] = SCHEMA_VERSION
        result[f"{name}.schema.json"] = schema
    return result


def export_json_schemas(destination: Path | None = None) -> list[Path]:
    """Write all public schemas in stable filename and byte order."""
    target = destination or schemas_directory()
    target.mkdir(parents=True, exist_ok=True)
    expected_paths: list[Path] = []
    for filename, schema in generated_schemas().items():
        path = target / filename
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        expected_paths.append(path)
    return expected_paths


if __name__ == "__main__":
    export_json_schemas()
