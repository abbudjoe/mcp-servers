<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-10 Release Manifest

## Immutable identity

- Distribution: `qiskit-ibm-runtime-mcp-server`
- Version: `0.7.3`
- Tag: `runtime-research-v0.7.3`
- Annotated tag object: `66a9b66ac91e0031ba51e5576f28a6bd7410862a`
- Tested/peeled commit: `19dfc32862f99002e12bd6de824e5967c5227a85`
- Remote: `https://github.com/abbudjoe/mcp-servers.git`
- GitHub Release:
  `https://github.com/abbudjoe/mcp-servers/releases/tag/runtime-research-v0.7.3`

## Dependency pin

```text
qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.3#subdirectory=qiskit-ibm-runtime-mcp-server
```

An isolated CPython 3.12 installation from this exact public requirement
resolved to commit `19dfc32862f99002e12bd6de824e5967c5227a85` and passed the
installed-package probe for version `0.7.3`, 37 generated/packaged schemas,
`RecoveredJobReceipt`, `SubmissionRecovery`, status-insensitive snapshot
identity, and calibration-sensitive identity. The downloaded GitHub Release
assets matched the preregistered wheel and sdist hashes below.

## Evidence hashes

| Artifact | SHA-256 |
|---|---|
| `uv.lock` | `44fbf8f39ba02abf2708687bdf7f428e89bea7da408c68f82019a931d3a5b31a` |
| `qiskit_ibm_runtime_mcp_server-0.7.3-py3-none-any.whl` | `48b3dcc06b8d56186a42bd940c5a67dac7f2207572df4068a56f24d539425bab` |
| `qiskit_ibm_runtime_mcp_server-0.7.3.tar.gz` | `111ffffc3c7e2716953b4b7a68b43d5819328a75b4688e20b4507811e23d3e05` |

The build used `SOURCE_DATE_EPOCH=1784073600`. Two independent builds produced
the exact hashes above. Both the wheel and sdist passed isolated Python 3.12
installs and exposed version `0.7.3`, all 37 schemas, typed recovery, and
corrected snapshot identity. The annotated tag repeats the three final hashes.

## Safety coverage

The supported Python 3.10–3.14 matrix enforced branch-only coverage per module:

- Runtime suite: 408 passed and one explicitly gated read-only integration skip
  on every Python 3.10–3.14 interpreter;
- approval consumption: 100.00%;
- budgeting and approval validation: 91.07%;
- Primitive result parsing: 90.91%;
- secret handling: 100.00%.

## Superseded snapshot identity

Release `0.7.2` remains immutable at tag `runtime-research-v0.7.2`. Its snapshot
hash includes typed backend-status observations, so queue movement can invalidate
an otherwise unchanged target/calibration identity. Preserve 0.7.2 evidence under
that pin, but generate a new snapshot, plan, and approval for 0.7.3.

## Superseded recovery contract

Release `0.7.1` remains immutable at tag `runtime-research-v0.7.1`, tag object
`6ae1ff73b3a5541f5f49e7ce97ef2fbcd6ca9351`, peeled commit
`664a44c086f49c15279f814e205b15970e689fe0`. It is not a Workstream 2 recovery
pin because its restart inventory lacks typed plan/partition/PUB identity and a
required wrapper-owned submission timestamp.
