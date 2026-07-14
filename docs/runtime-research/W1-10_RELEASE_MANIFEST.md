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
- Version: `0.7.2`
- Tag: `runtime-research-v0.7.2`
- Annotated tag object: `0182e8b254b7e357b3738161d0cd9a6a720d3f01`
- Tested/peeled commit: `de40ebfcc28946c6424e6d54a8399aac111b2daa`
- Remote: `https://github.com/abbudjoe/mcp-servers.git`
- GitHub Release:
  `https://github.com/abbudjoe/mcp-servers/releases/tag/runtime-research-v0.7.2`

## Dependency pin

```text
qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.2#subdirectory=qiskit-ibm-runtime-mcp-server
```

An isolated CPython 3.12 installation from this exact requirement resolved to
the tested commit and passed the installed-package probe for version `0.7.2`,
37 generated/packaged schemas, `RecoveredJobReceipt`, and
`SubmissionRecovery` (`REMOTE_PIN_INSTALL_OK 0.7.2 37
de40ebfcc28946c6424e6d54a8399aac111b2daa`).

## Evidence hashes

| Artifact | SHA-256 |
|---|---|
| `uv.lock` | `e54af79a029c06b4768dd5aafa22faa960e286ee9a4b84003a950ee7180521e4` |
| `qiskit_ibm_runtime_mcp_server-0.7.2-py3-none-any.whl` | `128f5a9a3cbf3863b9184b7bab7f561da835ac13ac1068ce77d014f6e0da59f7` |
| `qiskit_ibm_runtime_mcp_server-0.7.2.tar.gz` | `39a76afd2c7740dc2299165886d1c631f0a15149f5bc1c870e292488c8139509` |

The build used `SOURCE_DATE_EPOCH=1784059200`. Both the wheel and sdist passed
isolated Python 3.12 installs and exposed version `0.7.2` and all 37 schemas.
The annotated tag repeats the three hashes above.

## Safety coverage

The supported Python 3.10–3.14 matrix enforced branch-only coverage per module:

- Runtime suite: 405 passed and one explicitly gated read-only integration skip
  on every interpreter;
- approval consumption: 100.00%;
- budgeting and approval validation: 91.07%;
- Primitive result parsing: 90.91%;
- secret handling: 100.00%.

## Superseded recovery contract

Release `0.7.1` remains immutable at tag `runtime-research-v0.7.1`, tag object
`6ae1ff73b3a5541f5f49e7ce97ef2fbcd6ca9351`, peeled commit
`664a44c086f49c15279f814e205b15970e689fe0`. It is not a Workstream 2 recovery
pin because its restart inventory lacks typed plan/partition/PUB identity and a
required wrapper-owned submission timestamp.
