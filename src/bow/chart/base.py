"""
bow.chart.base — Chart base class.

Every bow chart extends this class.
Chart = pip package. Version and dependency management is left to pip.
Render logic is written in Python, default values are read from YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import yaml

from bow.chart.dependency import ChartDep, resolve_condition, get_dep_values
from bow.chart.values import deep_merge, merge_all_values
from bow.core.manifest import manifest, Manifest
from bow.core.resource import set_tracking


class Chart:
    """Bow chart base class.

    Subclasses must define:

    - ``name``: Chart name (must match the entry_points key)
    - ``version``: Semver string
    - ``requires``: ChartDep list (optional)
    - ``render(values)``: Method that creates resources

    Optional:
    - ``defaults_file``: Path to defaults.yaml
    - ``default_values()``: Default values as a Python dict

    Usage::

        class PostgreSQLChart(Chart):
            name = "postgresql"
            version = "16.4.0"

            def render(self, values):
                with Deployment(values["name"]):
                    ...
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = "0.0.0"
    description: ClassVar[str] = ""
    requires: ClassVar[list[ChartDep]] = []

    def default_values(self) -> dict[str, Any]:
        """Return default values.

        First looks for defaults.yaml next to the chart module,
        returns an empty dict if not found. Subclass may override.
        """
        # Look for defaults.yaml next to the chart module
        module_file = getattr(self.__class__, "__module__", None)
        if module_file:
            import importlib
            mod = importlib.import_module(self.__class__.__module__)
            if hasattr(mod, "__file__") and mod.__file__:
                defaults_path = Path(mod.__file__).parent / "defaults.yaml"
                if defaults_path.exists():
                    with open(defaults_path) as f:
                        data = yaml.safe_load(f)
                    return data if isinstance(data, dict) else {}
        return {}

    def render(self, values: dict[str, Any]) -> None:
        """Create resources. Subclass MUST implement."""
        raise NotImplementedError(f"{self.__class__.__name__}.render()")

    def template(
        self,
        value_files: list[str | Path] | None = None,
        set_args: list[str] | None = None,
        namespace: str | None = None,
    ) -> Manifest:
        """Render the chart and return a Manifest (without applying).

        This method:
        1. Merges values (defaults → files → --set)
        2. Resolves and renders dependencies
        3. Calls the chart's own render()
        4. Returns a Manifest
        """
        # Values merge
        defaults = self.default_values()
        values = merge_all_values(
            defaults,
            value_files or [],
            set_args or [],
        )

        # Tracking labels
        set_tracking(chart=self.name, version=self.version)

        with manifest() as m:
            # Dependency'leri render et
            self._render_dependencies(values)
            # Render the chart's own resources
            self.render(values)

        return m

    def _render_dependencies(self, values: dict[str, Any]) -> None:
        """Render dependency charts."""
        from bow.chart.registry import get_chart

        for dep in self.requires:
            # Condition check
            if not resolve_condition(values, dep.condition):
                continue

            if not dep.deploy:
                continue

            # Find dependency chart
            dep_chart = get_chart(dep.chart)
            if dep_chart is None:
                raise RuntimeError(
                    f"Dependency chart '{dep.chart}' not found. "
                    f"Install it with: pip install bow-{dep.chart}"
                )

            # Dependency values
            dep_values = get_dep_values(values, dep)

            # Render
            dep_chart.render(dep_values)

    def info(self) -> dict[str, Any]:
        """Return chart information (for bow inspect)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "defaults": self.default_values(),
            "dependencies": [
                {
                    "chart": d.chart,
                    "deploy": d.deploy,
                    "condition": d.condition,
                }
                for d in self.requires
            ],
        }
