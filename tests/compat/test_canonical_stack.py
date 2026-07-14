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

"""Fail-fast guards for the W1-01 canonical scientific stack."""

from __future__ import annotations

import asyncio
import io
import sys
from importlib.metadata import version
from inspect import Parameter, signature
from pathlib import Path

import numpy as np
import tomllib
from fastmcp import FastMCP
from qiskit import qpy
from qiskit.circuit import QuantumCircuit
from qiskit.circuit.library import XGate
from qiskit.primitives.containers import (
    BitArray,
    DataBin,
    EstimatorPub,
    PrimitiveResult,
    PubResult,
    SamplerPub,
    SamplerPubResult,
)
from qiskit.transpiler import InstructionProperties, Target
from qiskit_ibm_runtime import (
    Batch,
    EstimatorV2,
    QiskitRuntimeService,
    SamplerV2,
)
from qiskit_ibm_runtime.ibm_backend import IBMBackend
from qiskit_ibm_runtime.options import EstimatorOptions, SamplerOptions


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_VERSIONS = {
    "fastmcp": "3.4.4",
    "numpy": "2.4.6",
    "qiskit": "2.4.2",
    "qiskit-gym": "0.4.1",
    "qiskit-ibm-runtime": "0.45.1",
    "qiskit-ibm-transpiler": "0.18.0",
    "qiskit-qasm3-import": "0.6.0",
    "qiskit-serverless": "0.30.1",
}


def _parameters(callable_object: object) -> dict[str, Parameter]:
    """Return an inspectable parameter mapping with a useful failure surface."""
    return dict(signature(callable_object).parameters)


def test_canonical_python_and_package_versions() -> None:
    """The scientific reference must not silently float to another stack."""
    assert sys.version_info[:3] == (3, 12, 12), (
        "W1-01 requires CPython 3.12.12; use the canonical-lock CI job or "
        "`uv sync --locked --python 3.12.12 --all-packages --all-groups`."
    )
    installed = {package: version(package) for package in CANONICAL_VERSIONS}
    assert installed == CANONICAL_VERSIONS, (
        "Canonical package drift detected. Update the compatibility report, "
        "API guards, root constraints, lock, and lock hash together."
    )


def test_root_constraints_are_the_single_lock_control_plane() -> None:
    """Exact workspace constraints and one root lock prevent split-brain locks."""
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    constraints = project["tool"]["uv"]["constraint-dependencies"]
    expected_constraints = {
        f"{package}=={package_version}"
        for package, package_version in CANONICAL_VERSIONS.items()
        if package != "numpy"
    }
    expected_constraints.update(
        {
            "numpy==2.2.6; python_version < '3.11'",
            "numpy==2.4.6; python_version >= '3.11'",
        }
    )
    assert set(constraints) == expected_constraints
    assert not list(REPOSITORY_ROOT.glob("*/uv.lock")), (
        "Nested uv.lock files are unsupported; regenerate only the root workspace lock."
    )


def test_primitive_v2_pub_and_result_shapes() -> None:
    """Guard the PUB coercion and per-PUB result containers used by W1-06."""
    sampler_parameters = _parameters(SamplerV2.run)
    estimator_parameters = _parameters(EstimatorV2.run)
    assert tuple(sampler_parameters) == ("self", "pubs", "shots")
    assert sampler_parameters["shots"].kind is Parameter.KEYWORD_ONLY
    assert tuple(estimator_parameters) == ("self", "pubs", "precision")
    assert estimator_parameters["precision"].kind is Parameter.KEYWORD_ONLY

    measured = QuantumCircuit(1, 1)
    measured.measure(0, 0)
    sampler_pub = SamplerPub.coerce((measured,), shots=128)
    estimator_pub = EstimatorPub.coerce((QuantumCircuit(1), "Z"), precision=0.05)
    assert sampler_pub.shots == 128
    assert estimator_pub.precision == 0.05

    samples = BitArray.from_samples(["0", "1"], num_bits=1)
    sampler_result = SamplerPubResult(
        DataBin(meas=samples), metadata={"circuit_metadata": {"pub_id": "s0"}}
    )
    estimator_result = PubResult(
        DataBin(
            shape=(1,),
            evs=np.asarray([0.25]),
            stds=np.asarray([0.01]),
            extension_field={"preserve": True},
        ),
        metadata={"target_precision": 0.05, "pub_id": "e0"},
    )
    result = PrimitiveResult([sampler_result, estimator_result], metadata={"version": 2})
    assert len(result) == 2
    assert result[0].data.meas.num_shots == 2
    assert result[1].data.extension_field == {"preserve": True}
    assert result.metadata == {"version": 2}


def test_batch_backend_properties_and_target_shapes() -> None:
    """Guard execution-mode and backend snapshot APIs without contacting IBM."""
    batch_parameters = _parameters(Batch)
    assert tuple(batch_parameters) == ("backend", "max_time", "create_new")
    assert batch_parameters["create_new"].kind is Parameter.KEYWORD_ONLY
    assert tuple(_parameters(Batch.from_id)) == ("session_id", "service")

    property_parameters = _parameters(IBMBackend.properties)
    assert tuple(property_parameters) == ("self", "refresh", "datetime")
    assert isinstance(IBMBackend.target, property)
    backend_parameters = _parameters(QiskitRuntimeService.backend)
    assert tuple(backend_parameters) == (
        "self",
        "name",
        "instance",
        "use_fractional_gates",
        "calibration_id",
    )

    target = Target(num_qubits=2)
    target.add_instruction(XGate(), {(0,): InstructionProperties(duration=2.5e-8, error=1e-4)})
    target_parameters = _parameters(Target.instruction_supported)
    assert "check_angle_bounds" in target_parameters
    assert target.instruction_supported("x", (0,))
    assert not target.instruction_supported("x", (1,))


def test_qpy_round_trip_and_format_version() -> None:
    """Guard QPY list semantics, metadata fidelity, and the qualified writer format."""
    dump_parameters = _parameters(qpy.dump)
    assert tuple(dump_parameters) == (
        "programs",
        "file_obj",
        "metadata_serializer",
        "use_symengine",
        "version",
        "annotation_factories",
    )
    assert dump_parameters["version"].default == 17
    assert tuple(_parameters(qpy.load)) == (
        "file_obj",
        "metadata_deserializer",
        "annotation_factories",
    )

    original = QuantumCircuit(2, name="canonical-guard", metadata={"source": "guard"})
    original.h(0)
    original.cx(0, 1)
    payload = io.BytesIO()
    qpy.dump(original, payload)
    payload.seek(0)
    loaded = qpy.load(payload)
    assert len(loaded) == 1
    assert loaded[0] == original
    assert loaded[0].metadata == {"source": "guard"}


def test_runtime_options_public_shape() -> None:
    """Guard structured V2 options and bulk update behavior."""
    sampler_fields = set(SamplerOptions.__dataclass_fields__)
    estimator_fields = set(EstimatorOptions.__dataclass_fields__)
    assert {
        "max_execution_time",
        "default_shots",
        "dynamical_decoupling",
        "execution",
        "twirling",
        "experimental",
    } <= sampler_fields
    assert {
        "max_execution_time",
        "default_precision",
        "default_shots",
        "resilience_level",
        "resilience",
        "execution",
        "twirling",
        "experimental",
    } <= estimator_fields

    sampler_options = SamplerOptions()
    sampler_options.update(default_shots=256, max_execution_time=60)
    estimator_options = EstimatorOptions()
    estimator_options.update(default_precision=0.02, max_execution_time=60)
    assert sampler_options.default_shots == 256
    assert estimator_options.default_precision == 0.02


def test_fastmcp_public_registration_and_listing_apis() -> None:
    """Guard only documented FastMCP APIs; private managers are unsupported."""
    server = FastMCP("canonical-stack-guard")

    @server.tool
    def add(left: int, right: int) -> int:
        """Add two integers."""
        return left + right

    @server.resource("config://canonical")
    def canonical_config() -> str:
        """Return a deterministic test resource."""
        return "locked"

    @server.resource("items://{item_id}")
    def canonical_item(item_id: str) -> str:
        """Return a deterministic templated resource."""
        return item_id

    @server.prompt
    def greet(name: str) -> str:
        """Return a deterministic prompt."""
        return f"Hello, {name}."

    tools = asyncio.run(server.list_tools())
    resources = asyncio.run(server.list_resources())
    prompts = asyncio.run(server.list_prompts())
    templates = asyncio.run(server.list_resource_templates())
    assert [tool.name for tool in tools] == ["add"]
    assert [str(resource.uri) for resource in resources] == ["config://canonical"]
    assert [prompt.name for prompt in prompts] == ["greet"]
    assert [str(template.uri_template) for template in templates] == ["items://{item_id}"]
    assert tuple(_parameters(FastMCP.list_tools)) == ("self", "run_middleware")
    assert tuple(_parameters(FastMCP.list_resources)) == ("self", "run_middleware")
    assert tuple(_parameters(FastMCP.list_prompts)) == ("self", "run_middleware")
    assert tuple(_parameters(FastMCP.list_resource_templates)) == ("self", "run_middleware")
