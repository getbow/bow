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


def resolve_condition(values: dict, condition: str | None) -> bool:
    """Check the condition string in the values dict.

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
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return True  # Key not found, default enabled
    return bool(current)


def get_dep_values(values: dict, dep: ChartDep) -> dict:
    """Extract values for the dependency chart.

    Uses the nested dict matching the dependency name in the
    main chart's values; falls back to default_values.
    """
    from bow.chart.values import deep_merge

    result = dict(dep.default_values)
    if dep.chart in values and isinstance(values[dep.chart], dict):
        result = deep_merge(result, values[dep.chart])
    return result
