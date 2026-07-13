# W1-02 Secure Authentication and Tool Profiles Ledger

Status: `successful`

## Target contract

The default Qiskit IBM Runtime MCP server is a research-only surface. It accepts
credentials only from `QISKIT_IBM_TOKEN` or the Qiskit Runtime saved-account
store without persisting or mutating either source. Every real Runtime client
requires an explicit `QISKIT_IBM_RUNTIME_MCP_INSTANCE`. The registered research
tool set contains no credential arguments, credential mutation, or account
deletion. Secret-like values are redacted at logging and public result
boundaries. No admin profile is shipped because W1-02 does not require any
administrative operation for research.

## DoD checklist

| DoD item | Status | Planned evidence |
| --- | --- | --- |
| Research server accepts no token argument | `met` | FastMCP input-schema and Python adapter-signature tests verify no registered tool has a token or credential argument. |
| Research server exposes no credential deletion or mutation tool | `met` | Exact allowlist tests verify setup/save/delete operations are absent; Runtime construction never calls `save_account`. |
| Explicit instance policy is enforced for live operations | `met` | Missing-instance test fails before Runtime client construction; configured and explicit-instance construction tests pass. |
| Secrets are redacted from logs and exceptions | `met` | Tests cover exact configured secrets without labels, contextual forms, compound secret fields, logging, nested public data, and detached exception chains. |
| Tool-registration tests distinguish research and optional admin profiles | `met` | Default profile is `research`; exact FastMCP registration matches the research allowlist; no unjustified admin profile is shipped. |

## Mapped implementation

- Authentication/runtime client factory: all DoD items except registration profile distinction.
- Research profile manifest and MCP adapter registration: token, mutation, and profile DoD items.
- Shared security/redaction boundary: log and exception redaction DoD item.
- Registration and negative-security suite: evidence for every DoD item.

## Evidence

- Focused security/profile smoke: `uv run pytest tests/test_security_profiles.py -q` — 10 passed.
- Full local suite: `uv run pytest -q` — 193 passed.
- Lint: `uv run ruff check src tests` — passed.
- Format: `uv run ruff format --check src tests` — passed.
- Type check: `uv run mypy src/` — passed for 6 source files.
- Security scan: `uv run bandit -q -r src` — passed (informational comment-parser warnings only).
- Artifact checks: `git diff --check` and notebook JSON validation — passed.
- Independent subagent review initially found incomplete raw-secret redaction and stale README guidance. Both were fixed; re-review result: `CLEAN`, with every W1-02 DoD item classified `met`.
- Post-review focused and full smokes repeated with the same 10/193 passing results.
- No network, cloud, credential migration, account mutation, or QPU calls were made.

## Exact research tool list

1. `active_account_info_tool`
2. `active_instance_info_tool`
3. `available_instances_tool`
4. `cancel_job_tool`
5. `find_optimal_qubit_chains_tool`
6. `find_optimal_qv_qubits_tool`
7. `get_backend_calibration_tool`
8. `get_backend_properties_tool`
9. `get_coupling_map_tool`
10. `get_job_results_tool`
11. `get_job_status_tool`
12. `least_busy_backend_tool`
13. `list_backends_tool`
14. `list_my_jobs_tool`
15. `list_saved_accounts_tool`
16. `run_estimator_tool`
17. `run_sampler_tool`
18. `usage_info_tool`
