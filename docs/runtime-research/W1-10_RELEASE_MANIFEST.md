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
- Version: `0.7.1`
- Tag: `runtime-research-v0.7.1`
- Tag object: `6ae1ff73b3a5541f5f49e7ce97ef2fbcd6ca9351`
- Tested/peeled commit: `664a44c086f49c15279f814e205b15970e689fe0`
- Remote: `https://github.com/abbudjoe/mcp-servers.git`

## Dependency pin

```text
qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.1#subdirectory=qiskit-ibm-runtime-mcp-server
```

An isolated CPython 3.12 installation from this exact requirement resolved to
the tested commit and passed the installed-package probe for version `0.7.1`,
35 generated/packaged schemas, and empty Runtime execution-span serialization.

## Evidence hashes

| Artifact | SHA-256 |
|---|---|
| `uv.lock` | `ee8dd3b8441558bf4c7f6bfc50548776104ad4a6565536c5d3104425a45379ef` |
| `qiskit_ibm_runtime_mcp_server-0.7.1-py3-none-any.whl` | `1b6341f913d8a9e826031fd1926cbde1dadfa972c4905a51f1315ab0659aaee6` |
| `qiskit_ibm_runtime_mcp_server-0.7.1.tar.gz` | `99b8bb03b4f33082a6ffa4a0e59aebe6668db942d3ebc8cf6cb8e05805461d14` |

The annotated tag repeats these hashes. Its human-written `Tested commit` line
contains an expanded-hash typo beginning with the same short `664a44c`; the Git
tag target is not affected. The remote peeled ref and clean-install resolver
both identify the authoritative commit recorded above. The published tag was
left immutable rather than rewritten to conceal the annotation error.

## Safety coverage

The supported Python 3.10–3.14 matrix enforced branch-only coverage per module:

- approval consumption: 100.00%;
- budgeting and approval validation: 91.07%;
- Primitive result parsing: 90.91%;
- secret handling: 100.00%.
