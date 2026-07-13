<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-00 Runtime Research Baseline Report

## Task ledger

| Field | Value |
|---|---|
| Task | W1-00 — Sync Upstream and Establish Baseline |
| Objective | Revalidate fork/upstream state, incorporate current upstream security fixes, and establish the Python 3.12 behavioral baseline before feature work. |
| Evidence date | 2026-07-13 |
| Status | `successful` |
| Canonical repository | `abbudjoe/mcp-servers` with `Qiskit/mcp-servers` as upstream |
| QPU policy | Forbidden for this task |

No research-wrapper feature or experiment-specific behavior was implemented in W1-00.

## Repository and upstream baseline

The refs were fetched from both remotes before comparison.

| Ref | Commit before sync | Commit after sync |
|---|---|---|
| Local `main` | `fbf6b8fc31ef9acfc5dc5bd16d6fb608f4f3380d` | `ba3dc9763ffefe56cdc559d4a88352dec62931c2` |
| Fork `origin/main` | `fbf6b8fc31ef9acfc5dc5bd16d6fb608f4f3380d` | `fbf6b8fc31ef9acfc5dc5bd16d6fb608f4f3380d` |
| `upstream/main` | `ba3dc9763ffefe56cdc559d4a88352dec62931c2` | `ba3dc9763ffefe56cdc559d4a88352dec62931c2` |

Before sync, the fork/local head was 0 commits ahead and 2 commits behind upstream. The
local branch was fast-forwarded with `git merge --ff-only upstream/main`; it is now identical
to upstream and 2 commits ahead of the fork remote. Nothing was pushed.

The refs were fetched again after the initial report commit and before the final report
refinement to establish this revalidation point:

| Revalidation ref | Commit | Divergence from `upstream/main` |
|---|---|---:|
| Fork default `origin/main` | `fbf6b8fc31ef9acfc5dc5bd16d6fb608f4f3380d` | 0 ahead, 2 behind |
| `upstream/main` | `ba3dc9763ffefe56cdc559d4a88352dec62931c2` | identical |
| Local/tracking `codex/w1-00-runtime-baseline` before final refinement | `ababb3f819ef8d236a3c951f0a7d9bfbfbce4cf4` | 1 ahead, 0 behind |

At that revalidation point, the one W1 branch commit beyond upstream was this report only and
the branch was identical to `origin/codex/w1-00-runtime-baseline`. The fork default branch
remained unsynchronized because W1-00 did not authorize pushing or rewriting `origin/main`.

The two incorporated commits are:

1. [`6ad63ed`](https://github.com/Qiskit/mcp-servers/commit/6ad63ed38bac7e68e42f878d22c0706406406b7c) — upgrade every server to FastMCP 3.2+ and migrate registration tests to public FastMCP APIs.
2. [`ba3dc97`](https://github.com/Qiskit/mcp-servers/commit/ba3dc9763ffefe56cdc559d4a88352dec62931c2) — merge [Qiskit/mcp-servers PR #220](https://github.com/Qiskit/mcp-servers/pull/220).

The upstream delta changes FastMCP constraints from `>=2.8.1,<3` to `>=3.2.0,<4`,
resolves FastMCP 3.4.4 in the root lock, and replaces private-manager assertions with
`list_tools()`, `list_resources()`, `list_prompts()`, and `list_resource_templates()`.
This agrees with the official
[FastMCP 2-to-3 migration guide](https://gofastmcp.com/getting-started/upgrading/from-fastmcp-2).
The upstream post-merge [CI run](https://github.com/Qiskit/mcp-servers/actions/runs/29236339908)
reports 24 successful checks.

The latest repository release notes were also reviewed. Meta-package
[0.11.0](https://github.com/Qiskit/mcp-servers/releases/tag/meta-v0.11.0) removes the retired
Code Assistant server; Runtime wrapper
[0.6.0](https://github.com/Qiskit/mcp-servers/releases/tag/runtime-v0.6.0) replaces the retired
`ibm_torino` backend, adds FastMCP instructions, prompts, and resource templates; and core Qiskit
wrapper [0.3.0](https://github.com/Qiskit/mcp-servers/releases/tag/qiskit-v0.3.0) adds FastMCP
instructions and prompts. PR #220 is newer than those tags. Its diff changes dependency and
test compatibility surfaces only: it contains no Qiskit transpiler behavior or IBM Runtime
submission/result implementation change.

## Locked Python 3.12 baseline

`uv lock --check` passed, and the complete workspace installed with
`uv sync --locked --python 3.12 --all-packages --all-groups`.

| Component | Locked/tested version |
|---|---:|
| Python | 3.12.12 |
| uv | 0.11.7 |
| Qiskit | 2.3.0 |
| Qiskit IBM Runtime | 0.43.1 |
| FastMCP | 3.4.4 |
| MCP Python SDK | 1.26.0 |
| Pydantic | 2.12.5 |
| Runtime wrapper package | 0.6.0 |
| Ruff | 0.14.14 |
| mypy | 1.19.1 |
| Bandit | 1.9.3 |
| pytest | 9.0.2 |

The exact locked Qiskit versions are behind current official releases: Qiskit
[2.5.0](https://github.com/Qiskit/qiskit/releases/tag/2.5.0) and Qiskit IBM Runtime
[0.47.0](https://github.com/Qiskit/qiskit-ibm-runtime/releases/tag/0.47.0). The lock was
not upgraded by W1-00 because compatibility qualification and API guards belong to W1-01.
Relevant exact-version references are the official Qiskit
[2.3.0 release](https://github.com/Qiskit/qiskit/releases/tag/2.3.0) and Runtime
[0.43.1 release](https://github.com/Qiskit/qiskit-ibm-runtime/releases/tag/0.43.1).

### Lock and CI inconsistencies for W1-01

- The root `uv.lock` is the effective workspace lock and passes a locked/offline check.
- Four package-local locks are stale and normally ignored by workspace discovery. They
  resolve old wrapper and FastMCP versions; the Runtime-local lock, for example, records
  wrapper 0.1.0, FastMCP 2.12.2, and Runtime 0.41.1.
- The root lock requires Python `<3.14` because the Gym and IBM Transpiler members require
  `<3.14`, while Runtime, Qiskit, and Docs CI jobs include Python 3.14. A locked 3.14 sync
  is structurally unsatisfiable under workspace discovery.
- CI requests `setup-uv` version `latest` and runs plain `uv sync` rather than a frozen or
  locked install.
- Ruff and mypy run on Python 3.12 but target Python 3.10 language semantics, consistent
  with the broad package support policy but different from the canonical-runtime target.

## Upstream and dependency security review

### Incorporated upstream fixes

FastMCP moved from 2.14.5 to 3.4.4. The locked versions are above the published fixes for:

- [CVE-2026-32871 / GHSA-vv7q-7jx5-f767](https://github.com/advisories/GHSA-vv7q-7jx5-f767) in FastMCP;
- [CVE-2026-49852](https://github.com/advisories/GHSA-gg9x-qcx2-xmrh) and
  [CVE-2026-48990](https://github.com/advisories/GHSA-wphv-vfrh-23q5) in joserfc;
- [CVE-2026-44681](https://github.com/advisories/GHSA-r95x-qfjj-fjj2) and
  [CVE-2026-41479](https://github.com/advisories/GHSA-w8p2-r796-3vmq) in Authlib.

FastMCP's official [3.2.0 release](https://github.com/PrefectHQ/fastmcp/releases/tag/v3.2.0)
also documents the public-API and security changes incorporated by the upstream patch.

### Unresolved dependency exposure

`pip-audit` was run against both the all-groups Python 3.12 environment and the exported,
locked Runtime production closure.

| Scope | Result |
|---|---|
| Full all-groups workspace environment | 129 advisory records in 34 packages |
| Runtime production closure | 27 advisory records in 9 packages |

The nine production-closure packages reported are `click`, `cryptography`, `idna`,
`pydantic-settings`, `pygments`, `pyjwt`, `python-dotenv`, `requests`, and `urllib3`.
Some records are duplicate aliases for the same underlying advisory. Two concrete
contradictions need immediate W1-01 resolution:

- PR #220 claims the Click command-injection hardening is incorporated, but the lock still
  contains Click 8.3.1; the official
  [Click 8.3.3 changelog](https://click.palletsprojects.com/en/stable/changes/#version-8-3-3)
  describes the relevant `shell=True` removal.
- PyJWT remains 2.11.0, below the 2.12.0 fix for
  [CVE-2026-32597 / GHSA-752w-5fwx-jx9f](https://github.com/advisories/GHSA-752w-5fwx-jx9f),
  even though FastMCP 3.2.0 requests that security bump.

FastMCP 3.4.4 also deliberately relaxed the HTTP Host/Origin guard defaults introduced in
3.4.3 for compatibility. Its
[release notes](https://github.com/PrefectHQ/fastmcp/releases/tag/v3.4.4) require HTTP
deployments to opt into explicit trusted hosts/origins. The current servers use stdio by
default, but any future HTTP profile must make that policy explicit.

### Secret scan

A detector scan of Git-tracked non-video files returned 26 `Secret Keyword` heuristic hits,
all in example READMEs or example agent code. Review found environment-variable names and
documented placeholders, not a credential-pattern or high-entropy detector hit. No obvious
committed credential was identified. This is baseline evidence, not a substitute for a
dedicated CI secret scanner.

## Runtime-wrapper security baseline

The repository's `.claude/skills/qiskit-mcp-dev/SKILL.md` correctly requires mocked IBM
services, but its instruction to follow existing patterns is unsafe until W1-02 establishes
new patterns. The current default research/control surface has these pre-existing P0 risks:

1. `setup_ibm_quantum_account_tool` accepts a raw token argument. Core account setup may
   persist that token with `save_account(..., overwrite=True)`, including a token obtained
   from the environment.
2. Credential deletion and job cancellation share the same default MCP server as research
   inspection and execution tools; there is no separate administrative profile.
3. There is no central secret-redaction boundary. Exceptions are interpolated into logs and
   MCP error responses, and saved/active account responses retain token suffixes.
4. Runtime service creation may search all instances, singleton reuse can retain stale
   instance ownership, and missing backends silently fall back to least-busy selection.
5. Sampler and Estimator submission paths have no approval receipt, budget policy,
   idempotency boundary, paid-fallback refusal, or `max_execution_time`.
6. Cost-amplifying defaults are enabled: Sampler DD/twirling and Estimator resilience/ZNE.
7. Runtime QPY loading decodes before enforcing resource limits and silently selects the
   first circuit from a multi-circuit payload.

These findings confirm the workstream changeset; they are not patched in W1-00 because they
map to W1-02, W1-05, and W1-08.

### CI and supply-chain risks

- Runtime CI injects `QISKIT_IBM_TOKEN` into 206 mock/fake-backed tests even though static
  inspection found no test requiring a real Runtime credential or network call.
- IBM Transpiler CI injects a real token into a 52-case integration suite. Thirty-eight cases
  can reach real backend/service resolution: 16 have outcomes that visibly depend on
  credentials, while 22 error-path cases pass without credentials for the wrong reason because
  an early authentication failure satisfies broad assertions. Only 14 cases are genuinely
  mocked or local-validation-only. Running the 38 service-coupled cases in ordinary CI
  conflicts with the repository rule that external IBM services be mocked in ordinary tests.
- There is no dependency-advisory or repository secret scan in CI.
- GitHub Actions are tag-pinned rather than commit-SHA-pinned; uv is requested as `latest`.
- The MCP registry publish workflow downloads and executes an unchecked `latest` binary in
  an OIDC-enabled publish job.

## Python 3.12 quality and test baseline

All commands removed `QISKIT_IBM_TOKEN` from the process environment. Credential-dependent
transpiler tests additionally ran with an isolated empty `HOME`, preventing use of saved
Qiskit credentials.

### Static gates

| Gate | Result |
|---|---|
| `ruff check` over all five `src` and `tests` trees | Pass |
| `ruff format --check` | Pass; 69 files already formatted |
| `mypy --config-file mypy.ini` over all five source trees | Pass; 34 source files |
| `bandit` over all five source trees | Pass; 10,104 lines, zero findings; 7 potential issues skipped by configured exclusions/comments |

### Tests and coverage

| Package/scope | Result | Line coverage |
|---|---|---:|
| Qiskit Docs, hermetic/default | 173 passed, 3 deselected | 95% |
| Qiskit IBM Runtime | 205 passed, 1 skipped | 89% |
| Qiskit IBM Transpiler, non-integration | 139 passed, 52 deselected | 93% |
| Core Qiskit MCP | 102 passed | 85% |
| Qiskit Gym | 97 passed | 67% |
| Public Docs integration | 2 passed, 1 failed | not combined |
| Credential-isolated IBM Transpiler integration | 36 passed, 12 failed, 4 xfailed | not combined |

The hermetic baseline is **716 passed and 1 skipped**. Across every existing test, including
the separately invoked external suites, the observed baseline is **754 passed, 13 failed,
1 skipped, and 4 xfailed**.

Pre-existing failures and warnings:

- The Docs integration class shares a module-global `httpx.AsyncClient` across pytest's
  function-scoped event loops. The second live test failed with `Event loop is closed`; the
  same test passed alone. Ordinary CI hides this because Docs config deselects integration.
- Twelve IBM Transpiler integration tests require credentials/backend resolution and failed
  as expected under the isolated credential-free home. Of 36 passing cases, source review
  found 22 service-coupled false greens and only 14 genuinely local/mocked cases; four more
  credential-dependent hybrid cases xfailed. No primitive submission exists in this suite.
- Runtime tests passed but emitted unawaited-coroutine warnings from sync-wrapper tests.
- Core Qiskit tests emitted 47 deprecation warnings for the Runtime fractional-translation
  plugin, which is deprecated as of Runtime 0.42.0.

No test was deleted, weakened, or broadly suppressed.

## Reproducible command evidence

Commands ran from `/Users/joseph/mcp-servers` unless a package working directory is shown.
Exit codes are recorded explicitly because `pip-audit` returns 1 when it finds advisories and
the separately gated external test suites reproduce known baseline failures.

### Refs, sync, lock, and versions

| Command | Exit | Summary |
|---|---:|---|
| `git rev-parse HEAD origin/main upstream/main` | 0 | Before sync: local/fork `fbf6b8f`; upstream `ba3dc97`. |
| `git fetch --prune origin` | 0 | Fork tracking refs refreshed. |
| `git fetch --prune upstream` | 0 | Upstream tracking refs refreshed. |
| `git rev-list --left-right --count HEAD...origin/main` | 0 | `0 0` before sync. |
| `git rev-list --left-right --count HEAD...upstream/main` | 0 | `0 2` before sync. |
| `git merge --ff-only upstream/main` | 0 | Fast-forwarded local `main` to `ba3dc97`. |
| `UV_OFFLINE=true uv lock --check` | 0 | Resolved the existing 331-package lock without network access. |
| `uv sync --locked --python 3.12 --all-packages --all-groups` | 0 | Installed the complete locked workspace on CPython 3.12.12. |
| `env -u QISKIT_IBM_TOKEN uv run --locked python -c 'import sys; from importlib.metadata import version; print(sys.version); [print(f"{p}=={version(p)}") for p in ("qiskit", "qiskit-ibm-runtime", "fastmcp", "mcp", "pydantic", "ruff", "mypy", "bandit", "pytest")]'` | 0 | Printed only interpreter/package versions recorded above. |

### Static gates

The path arrays below expand to the exact paths supplied to the aggregated invocations:

```zsh
src_dirs=(
  qiskit-docs-mcp-server/src
  qiskit-ibm-runtime-mcp-server/src
  qiskit-ibm-transpiler-mcp-server/src
  qiskit-mcp-server/src
  qiskit-gym-mcp-server/src
)
test_dirs=(
  qiskit-docs-mcp-server/tests
  qiskit-ibm-runtime-mcp-server/tests
  qiskit-ibm-transpiler-mcp-server/tests
  qiskit-mcp-server/tests
  qiskit-gym-mcp-server/tests
)
```

| Command | Exit | Summary |
|---|---:|---|
| `env -u QISKIT_IBM_TOKEN uv run --locked ruff check "${src_dirs[@]}" "${test_dirs[@]}"` | 0 | All checks passed. |
| `env -u QISKIT_IBM_TOKEN uv run --locked ruff format --check "${src_dirs[@]}" "${test_dirs[@]}"` | 0 | 69 files already formatted. |
| `env -u QISKIT_IBM_TOKEN uv run --locked mypy --config-file mypy.ini "${src_dirs[@]}"` | 0 | No issues in 34 source files. |
| `env -u QISKIT_IBM_TOKEN uv run --locked bandit -c qiskit-ibm-runtime-mcp-server/pyproject.toml -r "${src_dirs[@]}"` | 0 | 10,104 lines scanned; zero findings. All member Bandit configurations have the same effective skip/exclude policy. |

### Test commands

The hermetic command was run separately from each listed package directory:

```zsh
env -u QISKIT_IBM_TOKEN \
  uv run --locked pytest tests/ -m 'not integration' \
  --cov=src --cov-report=term-missing
```

| Working directory | Exit | Result |
|---|---:|---|
| `qiskit-docs-mcp-server` | 0 | 173 passed, 3 deselected; 95% coverage. |
| `qiskit-ibm-runtime-mcp-server` | 0 | 205 passed, 1 skipped; 89% coverage. |
| `qiskit-ibm-transpiler-mcp-server` | 0 | 139 passed, 52 deselected; 93% coverage. |
| `qiskit-mcp-server` | 0 | 102 passed; 85% coverage. |
| `qiskit-gym-mcp-server` | 0 | 97 passed; 67% coverage. |

External test evidence:

| Working directory and command | Exit | Result |
|---|---:|---|
| Docs: `env -u QISKIT_IBM_TOKEN uv run --locked pytest tests/ -m integration -q --no-cov` | 1 | 2 passed, 1 failed, 173 deselected. |
| Docs diagnostic: `env -u QISKIT_IBM_TOKEN uv run --locked pytest tests/test_data_fetcher.py::TestIntegration::test_get_page_docs_live -m integration -q --no-cov` | 0 | The event-loop failure passes in isolation, confirming shared-client lifecycle as the suite-order root cause. |
| IBM Transpiler: `env -u QISKIT_IBM_TOKEN HOME="$isolated_home" uv run --locked pytest tests/ -m integration -q --no-cov`, where `isolated_home` came from `mktemp -d -t qiskit-w1-00-no-creds` | 1 | 36 passed, 12 credential-dependent failures, 4 xfailed, 139 deselected. The empty home prevented saved-credential discovery. |
| IBM Transpiler xfail audit: same isolated command with `--runxfail` | 1 | 36 passed, 16 credential-dependent failures, 139 deselected. This proves all four non-strict hybrid xfails mask the same pre-backend credential failure. |

### Security commands

| Command | Exit | Summary |
|---|---:|---|
| `uvx --from pip-audit pip-audit --path .venv/lib/python3.12/site-packages --progress-spinner off` | 1 | Full all-groups environment: 129 advisory records in 34 packages. |
| `uvx --from pip-audit pip-audit -r =(uv export --locked --package qiskit-ibm-runtime-mcp-server --no-dev --no-default-groups --no-emit-workspace --no-hashes --no-annotate --no-header) --no-deps --disable-pip --progress-spinner off` | 1 | Locked Runtime production closure: 27 advisory records in 9 packages. This command uses zsh process substitution and audits the exact pinned export. |
| `uvx --from detect-secrets detect-secrets scan $(git ls-files \| rg -v '\\.mp4$') \| jq '{version: .version, findings: [.results \| to_entries[] \| select(.value \| length > 0) \| {file: .key, count: (.value \| length), types: ([.value[].type] \| unique)}], total: ([.results[] \| length] \| add // 0)}'` | 0 | 26 keyword-only hits in example files; no candidate values were emitted. |

An initial `detect-secrets scan --all-files` attempt was stopped after it expanded into the
new `.venv`; its output is not used as evidence. The tracked-file command above is the
completed repository scan.

## Independent conformance review and post-review smoke

An independent assembly reviewer checked the report against the W1-00 prompt, roadmap,
definitions of done, and API/security contracts. The first review classified the execution
gate as partial because the report did not yet preserve sufficiently exact command and
offline-lock evidence. The evidence section was corrected, `UV_OFFLINE=true uv lock
--check` was run directly, and the same reviewer then returned a clean re-review with all
five W1-00 DoD items met and no remaining findings.

After that clean review, the following smoke gates were rerun with
`QISKIT_IBM_TOKEN` removed from the environment:

| Gate | Exit | Result |
|---|---:|---|
| `UV_OFFLINE=true uv lock --check` | 0 | Existing 331-package lock resolves offline. |
| `git diff --check` | 0 | No whitespace errors. |
| Docs hermetic test suite | 0 | 173 passed, 3 deselected. |
| Runtime hermetic test suite | 0 | 205 passed, 1 skipped; 19 pre-existing unawaited-coroutine warnings. |
| IBM Transpiler hermetic test suite | 0 | 139 passed, 52 deselected; 7 warnings. |
| Core Qiskit hermetic test suite | 0 | 102 passed; 47 pre-existing deprecation warnings. |
| Qiskit Gym hermetic test suite | 0 | 97 passed. |

Each post-review test used `env -u QISKIT_IBM_TOKEN uv run --locked pytest tests/ -m
'not integration' -q --no-cov` from its package directory. The reviewer made no network,
cloud, Runtime, or QPU call.

## Test classification for follow-up

The scan distinguishes tests that need a real credential from mocked tests that encode the
current raw-token contract. Placeholder values such as `test_token` are fixtures, not secrets.

### Credential-dependent outcomes and hidden service coupling

Sixteen IBM Transpiler integration tests have outcomes that visibly depend on credentials
when both `QISKIT_IBM_TOKEN` and saved Qiskit credentials are unavailable. Twelve fail
normally and four are hidden by unconditional, non-strict xfail markers:

| Test group | Count | Classification and remediation owner |
|---|---:|---|
| `tests/integration/test_mcp_server.py::TestEndToEndScenarios::test_complete_synthesis_pass` | 1 | W1-01 must gate authenticated integration separately; W1-02 must remove account setup/token mutation from the research profile. |
| `tests/integration/test_qta.py`: the successful routing tests (including explicit coupling map) and successful Clifford, linear-function, permutation, and Pauli-network synthesis tests | 6 | W1-01 must replace ordinary-CI credential dependence with deterministic fakes/fixtures, retaining any separately authorized external compatibility suite. |
| `tests/integration/test_sync.py`: successful routing, Clifford, linear-function, permutation, and Pauli-network sync-wrapper tests | 5 | W1-01 must apply the same deterministic/external-suite split and lock/API guards. |
| `tests/integration/test_qta.py`: four hybrid transpilation cases marked xfail | 4 | W1-01 must prevent non-strict xfails from masking authentication failures and move real-service behavior to a separately authorized external suite or deterministic fixture. |

Another 22 error-path tests across `tests/integration/test_qta.py` and
`tests/integration/test_sync.py` are service-coupled false greens. Source call order resolves
the backend before loading/validating the circuit, so a missing-credential error can satisfy
their broad wrong-backend or wrong-QASM assertions before the intended behavior is exercised.
With the CI token present, these cases can reach the real service. W1-01 must deterministically
fake service resolution for all 38 service-coupled cases and tighten these 22 assertions to
require the intended error source.

Only the remaining 14 cases are genuinely mocked or local-validation-only. Running the four
hybrid cases with `--runxfail` confirms they fail during credential-dependent `ibm_boston`
backend resolution, before hybrid transpilation behavior is exercised.

### Mocked tests that encode token/control-plane behavior

| Surface | Existing evidence | Classification and remediation owner |
|---|---|---|
| Runtime unit/integration fixtures | `tests/conftest.py`, `tests/test_server.py`, `tests/test_integration.py`, and `tests/test_sync.py` patch environment tokens or call account setup/initialization with token arguments. They are mocked and do not need a real token. | W1-02 must replace assertions that preserve raw-token arguments, implicit credential persistence, destructive account deletion, token-suffix disclosure, and implicit instance selection with research/admin profile and redaction contracts. |
| IBM Transpiler unit fixtures | `tests/conftest.py` and unit tests for the Runtime service provider, utilities, and sync wrappers use placeholder token arguments and assert persistence/caching behavior. They are mocked and do not need a real token. | W1-02 owns the token-free research surface and explicit credential ownership; retain only tests appropriate to an optional admin/internal boundary. |
| FastMCP tool registration | Runtime account-management tool tests were weakened by the FastMCP 3 migration to callable-only checks. | W1-02 must add exact public `list_tools()` assertions for research/admin profiles, including negative token/setup/delete assertions. |
| CI secret injection | `.github/workflows/test.yml` injects `QISKIT_IBM_TOKEN` into both Runtime and IBM Transpiler jobs. | W1-01 removes it from ordinary Runtime CI and splits Transpiler hermetic checks from an explicitly authorized external suite; W1-02 ensures the research profile never accepts a token argument. |

Additional W1-01 work is to establish one canonical lock, add FastMCP/Primitive V2/QPY
compatibility guards, correct the Python 3.14 matrix contradiction, pin uv, and repair the
Docs integration client's event-loop lifecycle. Additional W1-02 coverage must include
environment authentication without persistence, exception/log redaction, explicit instance
ownership, and a network-denial fixture.

## Files changed

The upstream fast-forward changed these tracked files:

- all five server `pyproject.toml` files;
- registration tests in all five server test suites;
- root `uv.lock`.

W1-00 adds this report at `docs/runtime-research/baseline-report.md`. The supplied
`qiskit_wrapper_workstream_build_package/` directory was already untracked and was not
modified.

## Public contract changes

The upstream sync changes the supported FastMCP major version and therefore its Python
decorator/registration inspection contract. The server tests now use public FastMCP 3 APIs.
No MCP tool/resource name, Runtime wrapper function signature, result schema, or execution
behavior was intentionally changed by W1-00.

## Network and execution record

Network calls made:

- `git fetch`/remote-ref reads from the fork and Qiskit upstream;
- package downloads from the locked package indexes for the Python 3.12 environment;
- read-only GitHub and official FastMCP/Qiskit documentation/release/advisory requests;
- `pip-audit` advisory database queries;
- three public Qiskit Docs integration HTTP requests.

No authenticated IBM Runtime request was made. The credential-isolated transpiler tests
failed before backend access. No cloud job was launched, stopped, resized, or deleted.

**QPU calls made: none.**

## Unresolved risks and phase gate

W1-00 establishes a reviewable baseline but does not make the repository release-ready.
W1-01 is blocked from claiming a secure canonical lock until the production dependency
advisories, stale nested locks, Python 3.14 contradiction, uv pin, and compatibility guards
are resolved. W1-02 must replace the insecure research tool profile before any live wrapper
work proceeds. W1-09 remains forbidden without a human-approved immutable plan receipt.

## W1-00 Definition of Done

| DoD item | Status | Evidence |
|---|---|---|
| Current fork and upstream heads are recorded. | `met` | Exact refs and divergence are recorded above after live fetches. |
| Current upstream security and compatibility changes are incorporated or explicitly superseded. | `met` | Local fast-forward to `ba3dc97`; FastMCP 3 public-API migration and security delta reviewed. Remaining independent lock findings are assigned to W1-01. |
| Existing tests, lint, type checks, and security checks run on Python 3.12. | `met` | Static gates passed; all existing test scopes were invoked and exact passes/failures are recorded. |
| Pre-existing failures are documented before feature changes. | `met` | Docs event-loop failure, credential-dependent transpiler failures, warnings, lock/CI contradictions, and dependency advisories are recorded; no feature change was made. |
| No live QPU call occurs. | `met` | No primitive/job submission or authenticated Runtime request was made. |
