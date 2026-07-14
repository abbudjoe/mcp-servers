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

"""Build an immutable circuit contract without credentials or a QPU call."""

from pathlib import Path
from tempfile import TemporaryDirectory

from qiskit_ibm_runtime_mcp_server.core import CircuitLimits, LocalArtifactCAS
from qiskit_ibm_runtime_mcp_server.core import ingest_circuit
from qiskit_ibm_runtime_mcp_server.core.schemas import export_json_schemas


QASM3 = """OPENQASM 3.0;
include "stdgates.inc";
bit[2] c;
qubit[2] q;
h q[0];
cx q[0], q[1];
c = measure q;
"""


def main() -> None:
    """Persist one exact circuit and export its versioned contract schemas."""
    with TemporaryDirectory(prefix="qiskit-runtime-contract-") as temporary:
        root = Path(temporary)
        sink = LocalArtifactCAS(root / "artifacts")
        ingested = ingest_circuit(
            QASM3,
            circuit_format="qasm3",
            sink=sink,
            limits=CircuitLimits(max_qubits=8, max_operations=100),
        )
        schema_paths = export_json_schemas(root / "schemas")

        print(f"circuit_hash={ingested.artifact.circuit_hash}")
        print(f"artifact_uri={ingested.artifact.artifact.storage_uri}")
        print(f"schema_version={ingested.artifact.schema_version}")
        print(f"exported_schemas={len(schema_paths)}")


if __name__ == "__main__":
    main()
