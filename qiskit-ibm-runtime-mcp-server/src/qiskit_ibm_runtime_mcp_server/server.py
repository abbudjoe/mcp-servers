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


"""
Qiskit IBM Runtime MCP Server

A Model Context Protocol server that provides access to IBM Quantum services
through Qiskit IBM Runtime, enabling AI assistants to interact with quantum
computing resources.

Dependencies:
- fastmcp
- qiskit-ibm-runtime
- qiskit
- python-dotenv
"""

import logging
from datetime import datetime
from typing import Any, Literal

from fastmcp import FastMCP
from qiskit_mcp_server.circuit_serialization import CircuitFormat

from qiskit_ibm_runtime_mcp_server.ibm_runtime import (
    active_account_info,
    active_instance_info,
    available_instances,
    cancel_job,
    DDSequenceType,
    find_optimal_qubit_chains,
    find_optimal_qv_qubits,
    get_backend_calibration,
    get_backend_properties,
    get_backend_snapshot,
    get_bell_state_circuit,
    get_coupling_map,
    get_ghz_state_circuit,
    get_job_results,
    get_job_status,
    get_quantum_random_circuit,
    get_service_status,
    get_superposition_circuit,
    least_busy_backend,
    list_backends,
    list_my_jobs,
    list_saved_accounts,
    QVScoringMetric,
    run_estimator,
    run_sampler,
    ScoringMetric,
    usage_info,
)
from qiskit_ibm_runtime_mcp_server.core.snapshots import FractionalGateMode
from qiskit_ibm_runtime_mcp_server.profiles import DEFAULT_TOOL_PROFILE
from qiskit_ibm_runtime_mcp_server.security import install_secret_redaction


# Configure logging
logging.basicConfig(level=logging.INFO)
install_secret_redaction(logging.getLogger())
logger = logging.getLogger(__name__)
install_secret_redaction(logger)

# Initialize MCP server
mcp = FastMCP(
    "Qiskit IBM Runtime",
    instructions="""\
This is the default research profile for IBM Quantum access through Qiskit IBM Runtime.

Getting started:
1. Configure QISKIT_IBM_RUNTIME_MCP_INSTANCE explicitly.
2. Authenticate with QISKIT_IBM_TOKEN or existing Qiskit saved credentials. \
Credentials are never accepted by tools or persisted by this server.
3. Use list_backends_tool to see available backends, or least_busy_backend_tool \
to quickly find one with a short queue.

Execution safety:
- Direct run_sampler_tool and run_estimator_tool submission is disabled. They are \
deprecated compatibility stubs and return an error without creating a job.
- Live work must be prepared outside the MCP surface with the typed SubmissionPlan, \
ApprovalReceipt, and ApprovedBatchExecutor API.
- Use get_job_status_tool and get_job_results_tool only for already-submitted jobs.
- circuits:// resources are generic circuit inputs; retrieving one never authorizes \
or submits Runtime work.

Backend analysis:
- Use get_backend_properties_tool for static info (processor type, basis gates, \
qubit count).
- Use get_backend_calibration_tool for live calibration data (T1, T2, gate \
errors, faulty qubits).
- Use find_optimal_qubit_chains_tool or find_optimal_qv_qubits_tool to select \
the highest-fidelity qubits for your experiment.

Account management:
- Use available_instances_tool to see accessible instances and usage_info_tool \
to check quota and consumption.\
""",
)

tool_profile = DEFAULT_TOOL_PROFILE


# Tools
@mcp.tool()
async def list_backends_tool() -> dict[str, Any]:
    """List available IBM Quantum backends."""
    return await list_backends()


@mcp.tool()
async def least_busy_backend_tool() -> dict[str, Any]:
    """Find the least busy operational backend."""
    return await least_busy_backend()


@mcp.tool()
async def get_backend_properties_tool(backend_name: str) -> dict[str, Any]:
    """Get detailed properties of a specific backend.

    Args:
        backend_name: Name of the backend (e.g., 'ibm_brisbane')

    Returns:
        Backend properties including:
        - num_qubits: Number of qubits on the backend
        - simulator: Whether this is a simulator backend
        - operational: Current operational status
        - pending_jobs: Number of jobs in the queue
        - processor_type: Processor family (e.g., 'Eagle r3', 'Heron')
        - backend_version: Backend software version
        - basis_gates: Native gates supported (e.g., ['cx', 'id', 'rz', 'sx', 'x'])
        - coupling_map: Qubit connectivity as list of [control, target] pairs
        - max_shots: Maximum shots per circuit execution
        - max_experiments: Maximum circuits per job

    Note:
        For time-varying calibration data (T1, T2, gate errors, faulty qubits),
        use get_backend_calibration_tool instead.
        For detailed connectivity analysis (adjacency list, bidirectional check)
        or fake backend support, use get_coupling_map_tool instead.
    """
    return await get_backend_properties(backend_name)


@mcp.tool()
async def get_backend_snapshot_tool(
    backend_name: str,
    properties_at: datetime | None = None,
    fractional_gate_mode: FractionalGateMode = "disabled",
    dynamic_circuits: bool = False,
    pec: bool = False,
    pea: bool = False,
    gate_twirling: bool = False,
) -> dict[str, Any]:
    """Get a complete current or historical backend metadata snapshot.

    Args:
        backend_name: Explicit IBM backend name. No backend is selected implicitly.
        properties_at: Optional timezone-aware historical calibration timestamp.
        fractional_gate_mode: ``disabled`` for control flow, ``enabled`` for
            fractional gates, or ``all`` to inspect both target surfaces.
        dynamic_circuits: Whether the intended workload requires dynamic circuits.
        pec: Whether the intended workload enables probabilistic error cancellation.
        pea: Whether the intended workload enables probabilistic error amplification.
        gate_twirling: Whether the intended workload enables gate twirling.

    Returns:
        A versioned snapshot containing every target instruction/qargs tuple,
        every physical qubit, calibrations, faults, provenance, and stable hashes.

    Note:
        This tool is metadata-only. Fractional mode ``enabled`` is rejected with
        dynamic circuits, PEC, PEA, or gate twirling.
    """
    return await get_backend_snapshot(
        backend_name=backend_name,
        properties_at=properties_at,
        fractional_gate_mode=fractional_gate_mode,
        dynamic_circuits=dynamic_circuits,
        pec=pec,
        pea=pea,
        gate_twirling=gate_twirling,
    )


@mcp.tool()
async def get_backend_calibration_tool(
    backend_name: str, qubit_indices: list[int] | None = None
) -> dict[str, Any]:
    """Get calibration data for a backend including T1, T2 times and error rates.

    Args:
        backend_name: Name of the backend (e.g., 'ibm_brisbane')
        qubit_indices: Optional list of specific qubit indices to get data for.
                      If not provided, returns data for every backend qubit.

    Returns:
        Calibration data including:
        - T1 and T2 coherence times (in microseconds)
        - Qubit frequency (in GHz)
        - Readout errors for each qubit
        - Gate errors for common gates (x, sx, cx, etc.)
        - faulty_qubits: List of non-operational qubit indices
        - faulty_gates: List of non-operational gates with affected qubits
        - Last calibration timestamp

    Note:
        For static backend info (processor_type, backend_version, quantum_volume),
        use get_backend_properties_tool instead.
    """
    return await get_backend_calibration(backend_name, qubit_indices)


@mcp.tool()
async def get_coupling_map_tool(backend_name: str) -> dict[str, Any]:
    """Get the coupling map (qubit connectivity) for an IBM Quantum backend.

    Supports both real backends (requires credentials) and fake backends (no credentials).
    Use 'fake_' prefix for offline testing without IBM Quantum credentials.

    Args:
        backend_name: Name of the backend. Examples:
            - Real backends: 'ibm_brisbane', 'ibm_fez' (requires credentials)
            - Fake backends: 'fake_brisbane', 'fake_sherbrooke' (no credentials needed)

    Returns:
        Coupling map details including:
        - num_qubits: Total qubit count
        - edges: List of [control, target] qubit connection pairs
        - bidirectional: Whether all connections work in both directions
        - adjacency_list: Neighbor mapping for each qubit (key: qubit index as string)
        - source: 'fake_backend' if using a fake backend (only present for fake backends)

    Use cases:
        - Identify physically connected qubits for circuit optimization
        - Plan qubit assignments to minimize SWAP gates
        - Understand backend architecture for advanced optimization
        - Test circuit routing offline with fake backends

    Note:
        For processor type and other backend info, use get_backend_properties_tool.
    """
    return await get_coupling_map(backend_name)


@mcp.tool()
async def find_optimal_qubit_chains_tool(
    backend_name: str,
    chain_length: int = 5,
    num_results: int = 5,
    metric: ScoringMetric = "two_qubit_error",
) -> dict[str, Any]:
    """Find optimal linear qubit chains for quantum experiments.

    Algorithmically identifies the best qubit chains based on coupling map
    connectivity and calibration data. Essential for experiments requiring
    linear qubit arrangements (e.g., variational algorithms, error correction).

    Args:
        backend_name: Name of the backend (e.g., 'ibm_brisbane')
        chain_length: Number of qubits in the chain (default: 5, range: 2-20)
        num_results: Number of top chains to return (default: 5, max: 20)
        metric: Scoring metric to optimize:
            - "two_qubit_error": Minimize sum of CX/ECR gate errors (default)
            - "readout_error": Minimize sum of measurement errors
            - "combined": Weighted combination of gate errors, readout, and coherence

    Returns:
        Ranked chains with detailed metrics:
        - chains: List of chain results, each containing:
            - rank: Position in ranking (1 = best)
            - qubits: Ordered list of qubit indices in the chain
            - score: Total score (lower is better)
            - qubit_details: T1, T2, readout_error for each qubit
            - edge_errors: Two-qubit gate error for each connection
        - total_chains_found: Total number of valid chains discovered
        - faulty_qubits: List of qubit indices excluded from chains

    Use cases:
        - Select qubits for variational quantum algorithms (VQE, QAOA)
        - Plan linear qubit layouts for error correction experiments
        - Identify high-fidelity qubit paths for state transfer
        - Optimize qubit selection for 1D physics simulations
    """
    return await find_optimal_qubit_chains(
        backend_name, chain_length, num_results, metric
    )


@mcp.tool()
async def find_optimal_qv_qubits_tool(
    backend_name: str,
    num_qubits: int = 5,
    num_results: int = 5,
    metric: QVScoringMetric = "qv_optimized",
) -> dict[str, Any]:
    """Find optimal qubit subgraphs for Quantum Volume experiments.

    Unlike linear chains, Quantum Volume benefits from densely connected qubit sets
    where qubits can interact with minimal SWAP operations. This tool finds
    connected subgraphs and ranks them by connectivity and calibration quality.

    Args:
        backend_name: Name of the backend (e.g., 'ibm_brisbane')
        num_qubits: Number of qubits in the subgraph (default: 5, range: 2-10)
        num_results: Number of top subgraphs to return (default: 5, max: 20)
        metric: Scoring metric to optimize:
            - "qv_optimized": Balanced scoring for QV (connectivity + errors + coherence)
            - "connectivity": Maximize internal edges and minimize path lengths
            - "gate_error": Minimize total two-qubit gate errors on internal edges

    Returns:
        Ranked subgraphs with detailed metrics:
        - subgraphs: List of subgraph results, each containing:
            - rank: Position in ranking (1 = best)
            - qubits: List of qubit indices in the subgraph (sorted)
            - score: Total score (lower is better)
            - internal_edges: Number of edges within the subgraph
            - connectivity_ratio: internal_edges / max_possible_edges
            - average_path_length: Mean shortest path between qubit pairs
            - qubit_details: T1, T2, readout_error for each qubit
            - edge_errors: Two-qubit gate error for each internal edge
        - total_subgraphs_found: Total number of connected subgraphs discovered
        - faulty_qubits: List of qubit indices excluded from subgraphs

    Use cases:
        - Select optimal qubits for Quantum Volume experiments
        - Find densely connected regions for random circuit sampling
        - Identify high-quality qubit clusters for variational algorithms
        - Plan qubit allocation for algorithms requiring all-to-all connectivity
    """
    return await find_optimal_qv_qubits(backend_name, num_qubits, num_results, metric)


@mcp.tool()
async def list_my_jobs_tool(limit: int = 10) -> dict[str, Any]:
    """List user's recent jobs."""
    return await list_my_jobs(limit)


@mcp.tool()
async def get_job_status_tool(job_id: str) -> dict[str, Any]:
    """Get status of a specific job."""
    return await get_job_status(job_id)


@mcp.tool()
async def get_job_results_tool(
    job_id: str,
    primitive: Literal["sampler", "estimator"] | None = None,
    pub_ids: list[str] | None = None,
    pub_shapes: list[list[int]] | None = None,
    artifact_directory: str | None = None,
    artifact_threshold_bytes: int = 1_000_000,
) -> dict[str, Any]:
    """Get complete shape-preserving Primitive V2 results from a completed job.

    Retrieves every returned PUB and DataBin key. Pass the primitive and the ordered
    pub_ids and pub_shapes returned by typed submission to preserve caller-owned identity
    and validate returned shapes. Omitting all three invokes a deprecated inference path.

    Use this tool for an already-submitted job with caller-owned PUB identity.
    First check the job status with get_job_status_tool, then retrieve results
    when the job status is DONE.

    Args:
        job_id: ID of the completed job.
        primitive: Explicit primitive kind; provide together with pub_ids.
        pub_ids: Ordered identities of every submitted PUB.
        pub_shapes: Ordered broadcast shapes of every submitted PUB.
        artifact_directory: Local content-addressed storage root for large arrays.
        artifact_threshold_bytes: Maximum canonical JSON size retained inline.

    Returns:
        Dictionary containing:
        - status: "success", "pending", or "error"
        - job_id: The job ID
        - job_status: Current status of the job
        - result: Versioned PrimitiveResultEnvelope with every ordered PUB
        - backend: Name of the backend used
        - execution_time: Quantum execution time in seconds (if available)
        - migration_warning: Present only when legacy identity inference was used
    """
    return await get_job_results(
        job_id,
        primitive=primitive,
        pub_ids=pub_ids,
        pub_shapes=pub_shapes,
        artifact_directory=artifact_directory,
        artifact_threshold_bytes=artifact_threshold_bytes,
    )


@mcp.tool()
async def cancel_job_tool(job_id: str) -> dict[str, Any]:
    """Cancel a specific job."""
    return await cancel_job(job_id)


@mcp.tool()
async def run_estimator_tool(
    circuit: str,
    observables: str | list[str] | list[tuple[str, float]],
    parameter_values: list[float] | None = None,
    backend_name: str | None = None,
    circuit_format: CircuitFormat = "auto",
    optimization_level: int = 1,
    resilience_level: int = 1,
    zne_mitigation: bool = True,
    zne_noise_factors: tuple[float, ...] | None = None,
) -> dict[str, Any]:
    """Return an error without submitting; retained as a deprecated compatibility stub.

    Live execution requires the Python ``SubmissionPlan`` / ``ApprovalReceipt`` /
    ``ApprovedBatchExecutor`` control plane.
    """
    return await run_estimator(
        circuit,
        observables,
        parameter_values,
        backend_name,
        circuit_format,
        optimization_level,
        resilience_level,
        zne_mitigation,
        zne_noise_factors,
    )


@mcp.tool()
async def list_saved_accounts_tool() -> dict[str, Any]:
    """List all IBM Quantum accounts saved on disk.

    Returns account information from ~/.qiskit/qiskit-ibm.json including account names
    and channels. Secret-bearing fields are redacted from the result.
    """
    return await list_saved_accounts()


@mcp.tool()
async def active_account_info_tool() -> dict[str, Any]:
    """Get information about the currently active IBM Quantum account.

    Returns details about the account being used in the current session, including
    channel, instance, and name. This is the account used for all quantum operations.
    Secret-bearing fields are redacted from the result.
    """
    return await active_account_info()


@mcp.tool()
async def active_instance_info_tool() -> dict[str, Any]:
    """Get the Cloud Resource Name (CRN) of the currently active instance.

    Returns the instance identifier determining which quantum backends and resources
    are accessible. Important for users with access to multiple instances.
    """
    return await active_instance_info()


@mcp.tool()
async def available_instances_tool() -> dict[str, Any]:
    """List all IBM Quantum instances available to the active account.

    Returns information about all instances (organizations, projects, or service plans)
    the user has access to, including CRN, plan type, and name. Each instance provides
    access to different quantum backends with different quotas.
    """
    return await available_instances()


@mcp.tool()
async def usage_info_tool() -> dict[str, Any]:
    """Get usage statistics and quota information for the active instance.

    Returns detailed metrics including job counts, quantum runtime consumption,
    quota limits, and billing period information. Useful for monitoring resource
    utilization and planning job submissions.
    """
    return await usage_info()


@mcp.tool()
async def run_sampler_tool(
    circuit: str,
    backend_name: str | None = None,
    shots: int = 4096,
    circuit_format: CircuitFormat = "auto",
    dynamical_decoupling: bool = True,
    dd_sequence: DDSequenceType = "XY4",
    twirling: bool = True,
    measure_twirling: bool = True,
) -> dict[str, Any]:
    """Return an error without submitting; retained as a deprecated compatibility stub.

    Live execution requires the Python ``SubmissionPlan`` / ``ApprovalReceipt`` /
    ``ApprovedBatchExecutor`` control plane.
    """
    return await run_sampler(
        circuit,
        backend_name,
        shots,
        circuit_format,
        dynamical_decoupling,
        dd_sequence,
        twirling,
        measure_twirling,
    )


##################################################
## MCP Prompts
## - https://modelcontextprotocol.io/docs/concepts/prompts
##################################################


@mcp.prompt()
def run_bell_state(backend_name: str = "") -> str:
    """Prepare a Bell-state input without authorizing or submitting Runtime work."""
    backend_clause = (
        f"on backend '{backend_name}'"
        if backend_name
        else "on the least busy backend (use least_busy_backend_tool to find it)"
    )
    return (
        f"Prepare a Bell-state experiment input {backend_clause}: "
        "1) Read circuits://bell-state, "
        "2) validate and ingest its circuit with the typed Python circuit boundary, "
        "3) create and human-review a bounded SubmissionPlan, "
        "4) submit only with a matching ApprovalReceipt through ApprovedBatchExecutor. "
        "The MCP run_sampler_tool is disabled and this prompt does not submit a job."
    )


@mcp.prompt()
def explore_backend(backend_name: str) -> str:
    """Explore an IBM Quantum backend's properties, calibration, and connectivity."""
    return (
        f"Explore the '{backend_name}' IBM Quantum backend: "
        f"1) Call get_backend_properties_tool with backend_name='{backend_name}' "
        "to get static properties (qubits, gates, processor type), "
        f"2) Call get_backend_calibration_tool with backend_name='{backend_name}' "
        "to get T1/T2 times and error rates, "
        f"3) Call get_coupling_map_tool with backend_name='{backend_name}' "
        "for qubit connectivity, "
        "4) Summarize the backend's key characteristics and any notable calibration issues."
    )


@mcp.prompt()
def monitor_job(job_id: str) -> str:
    """Monitor a running IBM Quantum job and retrieve its results when complete."""
    return (
        f"Monitor job '{job_id}' and retrieve results: "
        f"1) Call get_job_status_tool with job_id='{job_id}', "
        f"2) If status is DONE, call get_job_results_tool with job_id='{job_id}' "
        "to get measurement counts, "
        "3) If status is ERROR, report the error details from the status response, "
        "4) If still running, report the current status and suggest checking again shortly."
    )


# Resources
@mcp.resource("ibm://status", mime_type="text/plain")
async def get_service_status_resource() -> str:
    """Get current IBM Quantum service status."""
    return await get_service_status()


# Generic circuit input resources; retrieval never authorizes or submits work.
@mcp.resource("circuits://bell-state", mime_type="application/json")
def get_bell_state_resource() -> dict[str, Any]:
    """Get a generic Bell-state circuit input without submitting it.

    Returns a 2-qubit circuit that creates the Bell state |Φ+⟩ = (|00⟩ + |11⟩)/√2.
    This is the simplest demonstration of quantum entanglement.

    The caller must validate, plan, approve, and submit it through the typed
    Python control plane. ``run_sampler_tool`` is disabled.
    """
    return get_bell_state_circuit()


@mcp.resource("circuits://ghz-state", mime_type="application/json")
def get_ghz_state_resource() -> dict[str, Any]:
    """Get a generic 3-qubit GHZ circuit input without submitting it.

    Returns a circuit that creates the GHZ state |GHZ⟩ = (|000⟩ + |111⟩)/√2.
    This generalizes the Bell state to demonstrate 3-qubit entanglement.

    The caller must validate, plan, approve, and submit it through the typed
    Python control plane. ``run_sampler_tool`` is disabled.
    """
    return get_ghz_state_circuit(3)


@mcp.resource("circuits://random", mime_type="application/json")
def get_random_circuit_resource() -> dict[str, Any]:
    """Get a generic quantum-random circuit input without submitting it.

    Returns a 4-qubit circuit that generates truly random bits using quantum
    superposition. Each qubit is put in superposition and measured.

    The caller must validate, plan, approve, and submit it through the typed
    Python control plane. ``run_sampler_tool`` is disabled.
    """
    return get_quantum_random_circuit()


@mcp.resource("circuits://superposition", mime_type="application/json")
def get_superposition_resource() -> dict[str, Any]:
    """Get a generic single-qubit superposition input without submitting it.

    Returns a 1-qubit circuit that demonstrates quantum superposition by
    applying a Hadamard gate to create (|0⟩ + |1⟩)/√2.

    The caller must validate, plan, approve, and submit it through the typed
    Python control plane. ``run_sampler_tool`` is disabled.
    """
    return get_superposition_circuit()


##################################################
## MCP Resource Templates
## - https://modelcontextprotocol.io/docs/concepts/resources#resource-templates
##################################################


@mcp.resource("ibm://backends/{backend_name}", mime_type="application/json")
async def backend_properties_resource(backend_name: str) -> dict[str, Any]:
    """Get properties for a specific IBM Quantum backend."""
    return await get_backend_properties(backend_name)


@mcp.resource("ibm://jobs/{job_id}", mime_type="application/json")
async def job_status_resource(job_id: str) -> dict[str, Any]:
    """Get the status of a specific IBM Quantum job."""
    return await get_job_status(job_id)


def main() -> None:
    """Run the server."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()


# Assisted by watsonx Code Assistant
