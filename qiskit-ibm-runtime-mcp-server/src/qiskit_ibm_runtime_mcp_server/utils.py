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

"""Utility functions for the IBM Runtime MCP server.

This module provides the `with_sync` decorator for creating dual async/sync APIs.

Synchronous Execution
---------------------
All async functions decorated with `@with_sync` can be called synchronously
via the `.sync` attribute:

    from qiskit_ibm_runtime_mcp_server.ibm_runtime import list_backends

    # Async usage (in async context)
    result = await list_backends()

    # Sync usage (in a synchronous context such as a script or DSPy)
    result = list_backends.sync()

In an asynchronous context, including modern Jupyter notebooks, call the
function with ``await``. The synchronous wrapper intentionally does not mutate
or nest the caller's event loop.
"""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar


F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


def _run_async(coro_factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Helper to run async functions synchronously.

    The synchronous boundary owns its event loop. Calling it from an active
    event loop would require mutating or nesting that loop, which violates
    AnyIO's task ownership contract. Async callers must use ``await`` instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    raise RuntimeError(
        "The .sync interface cannot run inside an active event loop; "
        "await the asynchronous function instead."
    )


def with_sync(func: F) -> F:
    """Decorator that adds a `.sync` attribute to async functions for synchronous execution.

    Usage:
        @with_sync
        async def my_async_function(arg: str) -> Dict[str, Any]:
            ...

        # Async call
        result = await my_async_function("hello")

        # Sync call
        result = my_async_function.sync("hello")
    """

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        return _run_async(lambda: func(*args, **kwargs))

    func.sync = sync_wrapper  # type: ignore[attr-defined]
    return func
