"""
bow.chart.dependency — Chart dependency definition and resolver.

Each chart declares its dependencies as a ChartDep list.
The CLI resolves these dependencies at deploy time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChartDep:
    """A chart's dependency on another chart.

    Attributes:
        chart: Name of the dependency chart (entry_points key)
        deploy: If True, the dependency is also deployed
        condition: If this key is False in values, the dependency is skipped
        default_values: Default values sent to the dependency chart
    """

    chart: str
    deploy: bool = True
    condition: str | None = None
    default_values: dict[str, Any] = field(default_factory=dict)


def resolve_condition(values, condition: str | None) -> bool:
    """Check a dot-path condition against values.

    Works with both dict and Values objects.

    >>> resolve_condition({"postgresql": {"enabled": True}}, "postgresql.enabled")
    True
    >>> resolve_condition({"postgresql": {"enabled": False}}, "postgresql.enabled")
    False
    >>> resolve_condition({}, None)
    True
    """
    if condition is None:
        return True

    parts = condition.split(".")
    current: Any = values
    for part in parts:
        if _is_mapping(current) and part in current:
            current = current[part]
        else:
            return True  # Key missing = default enabled
    return bool(current)


def get_dep_values(values, dep: ChartDep) -> dict:
    """Extract dependency values from parent chart values.

    Works with both dict and Values objects.
    Returns a plain dict (dependency chart wraps it in Values itself).
    """
    from bow.chart.values import deep_merge

    result = dict(dep.default_values)
    raw = values._data if hasattr(values, "_data") else values
    if dep.chart in raw and isinstance(raw[dep.chart], dict):
        result = deep_merge(result, raw[dep.chart])
    return result


def _is_mapping(obj) -> bool:
    """Check if obj supports dict-like access (dict or Values)."""
    return isinstance(obj, dict) or hasattr(obj, "_data")
