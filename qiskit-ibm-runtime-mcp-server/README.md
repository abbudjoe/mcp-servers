# Qiskit IBM Runtime MCP Server

[![MCP Registry](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fregistry.modelcontextprotocol.io%2Fv0.1%2Fservers%2Fio.github.Qiskit%252Fqiskit-ibm-runtime-mcp-server%2Fversions%2Flatest&query=%24.server.version&label=MCP%20Registry&logo=modelcontextprotocol)](https://registry.modelcontextprotocol.io/?q=io.github.Qiskit%2Fqiskit-ibm-runtime-mcp-server)

<!-- mcp-name: io.github.Qiskit/qiskit-ibm-runtime-mcp-server -->

An MCP server and typed Python wrapper for reproducible IBM Quantum Runtime
workflows. The next release adds explicit resource ownership, immutable
plans and approvals, exact circuit boundaries, complete Primitive V2 PUB/result
contracts, crash-safe Batch receipt recovery, and content-addressed artifacts.

## Safety contract

- Live provider operations require an explicit
  `QISKIT_IBM_RUNTIME_MCP_INSTANCE`; the server never searches across instances.
- Credentials come from `QISKIT_IBM_TOKEN` or existing Qiskit saved credentials.
  The server does not accept token arguments or mutate saved accounts.
- Direct `run_sampler_tool` and `run_estimator_tool` calls are deprecated,
  non-submitting compatibility stubs. Live execution uses a canonical
  `SubmissionPlan`, a matching `ApprovalReceipt`, and `ApprovedBatchExecutor`.
- Paid fallback is denied by default. Every approved primitive job has a bounded
  `max_execution_time` and an immutable idempotency receipt.

## Install

Published releases can be installed with:

```bash
pip install qiskit-ibm-runtime-mcp-server
```

Supported Python versions are 3.10 through 3.14. The canonical tested
environment is Python 3.12 with the repository root `uv.lock`.

## Configure and run

```bash
export QISKIT_IBM_RUNTIME_MCP_INSTANCE="your-instance-crn"
# Optional when ~/.qiskit/qiskit-ibm.json already contains usable credentials:
export QISKIT_IBM_TOKEN="your-token"

qiskit-ibm-runtime-mcp-server
```

From a source checkout:

```bash
uv sync --frozen --group dev --group test
uv run qiskit-ibm-runtime-mcp-server
```

## Interfaces

The MCP surface provides read-only backend/account/usage discovery, job status
and result retrieval, explicit job cancellation, circuit resources, and disabled
legacy submission stubs. The Python contract API is imported from:

```python
from qiskit_ibm_runtime_mcp_server.core import (
    ApprovedBatchExecutor,
    BudgetPolicy,
    CircuitLimits,
    LocalArtifactCAS,
    RecoveredJobReceipt,
    SubmissionRecovery,
    SubmissionPlanner,
    ingest_circuit,
    parse_primitive_result,
)
```

Crash recovery requires the exact persisted `SubmissionPlan` and returns typed,
plan-ordered job receipts. It fails closed instead of reconstructing identity or
submission time from nullable provider metadata.

See [API.md](docs/API.md) for the supported contracts and
[runtime_contracts.py](examples/runtime_contracts.py) for an offline,
non-submitting example. Existing 0.6.x users should read
[MIGRATION.md](MIGRATION.md).

## Versioned schemas

Every public control/data model has a checked-in draft 2020-12 JSON Schema under
`src/qiskit_ibm_runtime_mcp_server/core/json_schemas/v1.0/`. Package version and
wire-schema version advance independently. The next release uses schema version
`1.0` for results, plans, budget policies, approvals, batches, artifacts,
circuits, and snapshots.

## Development gates

```bash
uv lock --check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy qiskit-ibm-runtime-mcp-server/src
uv run --frozen --package qiskit-ibm-runtime-mcp-server pytest
uv run --frozen --package qiskit-ibm-runtime-mcp-server bandit -c qiskit-ibm-runtime-mcp-server/pyproject.toml -r qiskit-ibm-runtime-mcp-server/src
```

Ordinary CI and examples do not submit QPU jobs. Live smoke tests are manual,
plan-bound, approval-bound, and separately budgeted.
