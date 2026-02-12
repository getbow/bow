"""
bow.chart.registry — Chart discovery.

Charts are pulled from OCI registries and pip-installed
into the active env's venv. Discovery from two sources:

1. entry_points in the active env's venv (installed from OCI)
2. System-wide entry_points (development mode, editable install)
3. Runtime register (for testing)

Pull → install flow:
    bow pull oci://reg/postgresql:16.4.0
      → download tar.gz → store in cache
      → unpack → pip install --target venv
      → entry_points auto-registered
    bow up postgresql
      → add venv to sys.path
      → entry_points("bow.charts") → discover
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bow.chart.base import Chart

# Runtime registry
_registry: dict[str, type[Chart]] = {}
_discovered = False


def _discover_charts() -> None:
    """Discover charts from entry_points.

    First adds the active env's venv to sys.path,
    then scans entry_points.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True

    # 1. Add active env's site-packages to sys.path
    _inject_env_path()

    # 2. Entry points discovery
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="bow.charts")
        for ep in eps:
            try:
                chart_cls = ep.load()
                _registry[ep.name] = chart_cls
            except Exception:
                pass
    except Exception:
        pass


def _inject_env_path() -> None:
    """Add the active env's site-packages to sys.path."""
    try:
        from bow.oci.env import get_env
        env = get_env()
        if env.exists():
            sp = env.site_packages
            sp_str = str(sp)
            if sp.exists() and sp_str not in sys.path:
                sys.path.insert(0, sp_str)

                # Invalidate importlib.metadata cache
                # so newly installed entry_points are visible
                try:
                    import importlib
                    importlib.invalidate_caches()
                except Exception:
                    pass
    except Exception:
        pass  # Env system may not be set up yet


def register_chart(chart_cls: type[Chart]) -> None:
    """Manually register a chart class (for testing/dev)."""
    _registry[chart_cls.name] = chart_cls


def get_chart(name: str) -> Chart | None:
    """Create an instance from a chart name."""
    _discover_charts()
    cls = _registry.get(name)
    if cls is None:
        return None
    return cls()


def get_chart_class(name: str) -> type[Chart] | None:
    """Get chart class by name."""
    _discover_charts()
    return _registry.get(name)


def list_charts() -> dict[str, type[Chart]]:
    """Return all registered charts."""
    _discover_charts()
    return dict(_registry)


def reset_registry() -> None:
    """Reset the registry. For testing."""
    global _discovered
    _registry.clear()
    _discovered = False
