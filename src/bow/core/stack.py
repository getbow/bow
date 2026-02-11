"""
bow.core.stack — Thread-local resource stack.

Inspired by Tagflow's document context.
Each `with Resource(...)` block pushes onto the stack,
pops on exit. Leaf nodes find their parent via _current().
"""

from __future__ import annotations

import threading
from typing import Any

_local = threading.local()


def _current_stack() -> list[Any]:
    """Return the active resource stack."""
    if not hasattr(_local, "stack"):
        _local.stack = []
    return _local.stack


def _current() -> Any | None:
    """Return the top resource on the stack (parent)."""
    stack = _current_stack()
    return stack[-1] if stack else None


def _push(resource: Any) -> None:
    """Push a resource onto the stack."""
    _current_stack().append(resource)


def _pop() -> Any:
    """Pop and return the top resource."""
    return _current_stack().pop()


def _collected() -> list[Any]:
    """Top-level resources collected by the manifest."""
    if not hasattr(_local, "collected"):
        _local.collected = []
    return _local.collected


def _set_collected(lst: list[Any]) -> None:
    """Replace the collected list (manifest context switch)."""
    _local.collected = lst


def _reset() -> None:
    """Reset stack and collected. For testing."""
    _local.stack = []
    _local.collected = []
