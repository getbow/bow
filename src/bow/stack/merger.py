"""
bow.stack.merger — Stack overlay merger.

Deep merges multiple -f files:
  bow up -f stack.yaml -f values.prod.yaml --set ...

Merge strategy:
  - First file must be the base stack (apiVersion, kind, metadata, components)
  - Subsequent files are overlays (only component values override)
  - --set is applied last

Overlay format:
    components:
      main-db:              # matches by component name
        values:
          replicas: 3
          storage: 200Gi
      redmine:
        values:
          replicas: 5
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bow.chart.values import deep_merge


def merge_stack_files(file_paths: list[str | Path]) -> dict[str, Any]:
    """Merge multiple stack/overlay files.

    The first file must be a complete stack definition.
    Subsequent files can override component values.

    Args:
        file_paths: File paths list (in precedence order)

    Returns:
        Merged stack dict
    """
    if not file_paths:
        raise ValueError("At least one file is required")

    # First file: base stack
    base = _load_yaml(file_paths[0])

    # Subsequent files: overlays
    for fp in file_paths[1:]:
        overlay = _load_yaml(fp)
        base = _merge_overlay(base, overlay)

    return base


def apply_set_to_stack(
    stack_data: dict[str, Any],
    set_args: list[str],
) -> dict[str, Any]:
    """Apply --set arguments to the stack.

    Format: components.<name>.values.<key>=<value>

    Example:
      --set components.main-db.values.storage=100Gi
      --set components.main-db.values.replicas=3
    """
    from bow.chart.values import parse_set_values

    if not set_args:
        return stack_data

    overrides = parse_set_values(set_args)
    return deep_merge(stack_data, overrides)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    with open(p) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {p}")
    return data


def _merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Apply an overlay to the base stack.

    The overlay supports two formats:

    Format 1 — Tam stack (apiVersion + components list):
        apiVersion: bow.io/v1
        components:
          - chart: postgresql
            name: main-db
            values:
              replicas: 3

    Format 2 — Component-only override (name → values mapping):
        components:
          main-db:
            values:
              replicas: 3
    """
    result = dict(base)

    if "components" not in overlay:
        return result

    overlay_components = overlay["components"]

    # Format 2: dict mapping (name → overrides)
    if isinstance(overlay_components, dict):
        result["components"] = _merge_components_dict(
            result.get("components", []),
            overlay_components,
        )
    # Format 1: list (tam component listesi)
    elif isinstance(overlay_components, list):
        result["components"] = _merge_components_list(
            result.get("components", []),
            overlay_components,
        )

    # Metadata overlay
    if "metadata" in overlay:
        result["metadata"] = deep_merge(
            result.get("metadata", {}),
            overlay["metadata"],
        )

    return result


def _merge_components_dict(
    base_components: list[dict],
    overlay_map: dict[str, dict],
) -> list[dict]:
    """Component dict overlay: name → values merge."""
    result = []
    for comp in base_components:
        comp_name = comp.get("name", comp.get("chart", ""))
        if comp_name in overlay_map:
            merged = deep_merge(comp, overlay_map[comp_name])
            result.append(merged)
        else:
            result.append(dict(comp))
    return result


def _merge_components_list(
    base_components: list[dict],
    overlay_components: list[dict],
) -> list[dict]:
    """Component list overlay: match by name and merge."""
    # Index base by name
    base_by_name: dict[str, dict] = {}
    for comp in base_components:
        name = comp.get("name", comp.get("chart", ""))
        base_by_name[name] = comp

    # Merge each component in the overlay
    result_by_name: dict[str, dict] = dict(base_by_name)
    for comp in overlay_components:
        name = comp.get("name", comp.get("chart", ""))
        if name in result_by_name:
            result_by_name[name] = deep_merge(result_by_name[name], comp)
        else:
            result_by_name[name] = comp

    # Preserve order (base order + new additions)
    ordered: list[dict] = []
    seen: set[str] = set()
    for comp in base_components:
        name = comp.get("name", comp.get("chart", ""))
        ordered.append(result_by_name[name])
        seen.add(name)
    for name, comp in result_by_name.items():
        if name not in seen:
            ordered.append(comp)
    return ordered
