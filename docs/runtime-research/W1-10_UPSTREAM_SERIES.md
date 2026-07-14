<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-10 Upstream Contribution Series

The contribution series is cumulative and based on current upstream commit
`8c1abcec04ea5d504cc178c42441c8363c6935b5`. Fork branch
`codex/upstream-base-8c1abce` preserves that exact base. Each draft PR targets
the base shown for its row so every review contains one dependency layer.

| Order | Draft PR | Head branch / commit | PR base | Scope |
|---:|---|---|---|---|
| 1 | [#1](https://github.com/abbudjoe/mcp-servers/pull/1) | `codex/upstream-01-stack-lock` / `050c92b` | `codex/upstream-base-8c1abce` | Canonical workspace lock and compatibility gate |
| 2 | [#2](https://github.com/abbudjoe/mcp-servers/pull/2) | `codex/upstream-02-runtime-security` / `3a46f5c` | `codex/upstream-01-stack-lock` | Explicit instance, credential, and tool-profile boundaries |
| 3 | [#3](https://github.com/abbudjoe/mcp-servers/pull/3) | `codex/upstream-03-runtime-contracts-artifacts` / `eb404da` | `codex/upstream-02-runtime-security` | Typed models, generic `runtime-contracts` schemas, artifact CAS |
| 4 | [#4](https://github.com/abbudjoe/mcp-servers/pull/4) | `codex/upstream-04-backend-snapshots` / `9d87c1b` | `codex/upstream-03-runtime-contracts-artifacts` | Complete reproducible backend snapshots |
| 5 | [#5](https://github.com/abbudjoe/mcp-servers/pull/5) | `codex/upstream-05-circuit-boundary` / `50f3bff` | `codex/upstream-04-backend-snapshots` | Exact circuit boundary and ISA validation |
| 6 | [#6](https://github.com/abbudjoe/mcp-servers/pull/6) | `codex/upstream-06-primitive-v2-contracts` / `7e03801` | `codex/upstream-05-circuit-boundary` | Ordered Primitive V2 PUB/result contracts |
| 7 | [#7](https://github.com/abbudjoe/mcp-servers/pull/7) | `codex/upstream-07-batch-lifecycle` / `1c7a4e9` | `codex/upstream-06-primitive-v2-contracts` | Batch lifecycle, idempotency, and recovery |
| 8 | [#8](https://github.com/abbudjoe/mcp-servers/pull/8) | `codex/upstream-08-qpu-budget-approval` / `f57962c` | `codex/upstream-07-batch-lifecycle` | QPU planning, budgets, and approvals |
| 9 | [#9](https://github.com/abbudjoe/mcp-servers/pull/9) | `codex/upstream-09-runtime-hardening` / `5f1cf14` | `codex/upstream-08-qpu-budget-approval` | Submission/result contract regressions and fixes |
| 10 | [#10](https://github.com/abbudjoe/mcp-servers/pull/10) | `codex/upstream-10-runtime-docs` / `d985202` | `codex/upstream-09-runtime-hardening` | Generic changelog, migration, API, and offline example |

All heads are published under `https://github.com/abbudjoe/mcp-servers`. The
series intentionally excludes `docs/runtime-research`, the W1-10 compatibility
handoff, provider/job evidence, the fork release pin, and preemptive upstream
version/registry changes. A per-delta added-line audit and a whole-tip audit
found none of the excluded workstream identifiers, fork URLs, release tag text,
or experiment-specific schema namespace.
