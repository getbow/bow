"""
bow.chart.registry — Chart discovery via entry_points.

Charts are installed as pip packages and discovered
via entry_points:

    [project.entry-points."bow.charts"]
    postgresql = "bow_postgresql:PostgreSQLChart"

Runtime programmatic registration is also supported
(for testing and development).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bow.chart.base import Chart

# Runtime registry (entry_points + manual)
_registry: dict[str, type[Chart]] = {}
_discovered = False


def _discover_charts() -> None:
    """Discover charts from entry_points."""
    global _discovered
    if _discovered:
        return
    _discovered = True

    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="bow.charts")
        for ep in eps:
            try:
                chart_cls = ep.load()
                _registry[ep.name] = chart_cls
            except Exception:
                pass  # Broken chart package, skip
    except Exception:
        pass


def register_chart(chart_cls: type[Chart]) -> None:
    """Manually register a chart class.

    Usage::

        register_chart(PostgreSQLChart)
    """
    _registry[chart_cls.name] = chart_cls


def get_chart(name: str) -> Chart | None:
    """Create an instance from a chart name."""
    _discover_charts()
    cls = _registry.get(name)
    if cls is None:
        return None
    return cls()


def list_charts() -> dict[str, type[Chart]]:
    """Return all registered charts."""
    _discover_charts()
    return dict(_registry)


def reset_registry() -> None:
    """Reset the registry. For testing."""
    global _discovered
    _registry.clear()
    _discovered = False
