"""
bow.stack.engine — Stack deploy engine.

Parses the stack file, merges overlays,
resolves references, renders charts in order.

    bow up -f stack.yaml -f values.prod.yaml --set ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bow.chart.registry import get_chart
from bow.chart.values import deep_merge
from bow.core.manifest import manifest, Manifest
from bow.core.resource import set_tracking
from bow.stack.parser import parse_stack_dict, StackSpec, StackParseError
from bow.stack.refs import resolve_refs, RefError
from bow.stack.merger import merge_stack_files, apply_set_to_stack


class StackError(Exception):
    """Stack deploy error."""
    pass


def render_stack(
    file_paths: list[str | Path],
    set_args: list[str] | None = None,
    namespace: str | None = None,
) -> Manifest:
    """Render stack files.

    Args:
        file_paths: stack.yaml + overlay files
        set_args: --set key=value list
        namespace: namespace override

    Returns:
        Combined Manifest of all components
    """
    # 1. Merge files
    merged_data = merge_stack_files(file_paths)

    # 2. Apply --set (stack-aware)
    if set_args:
        stack_set, chart_set = _split_set_args(set_args)
        if stack_set:
            # components.X.values.Y=Z format → apply as dict overlay
            _apply_component_overrides(merged_data, stack_set)
        # Remaining --set args are ignored for now
        # (could be used for stack-level metadata override etc.)

    # 3. Parse
    try:
        stack = parse_stack_dict(merged_data)
    except StackParseError as e:
        raise StackError(f"Stack parse error: {e}") from e

    # Namespace override
    if namespace:
        stack.namespace = namespace

    # 4. Resolve references
    try:
        resolved_components = resolve_refs(stack.components)
    except RefError as e:
        raise StackError(f"Reference error: {e}") from e

    # 5. Render charts in order
    with manifest() as m:
        for comp in resolved_components:
            chart = get_chart(comp.chart)
            if chart is None:
                raise StackError(
                    f"Chart '{comp.chart}' not found for component '{comp.name}'. "
                    f"Install it with: pip install bow-{comp.chart}"
                )

            # Tracking labels
            set_tracking(
                chart=comp.chart,
                version=chart.version,
                stack=stack.name,
            )

            # Chart defaults + component values merge
            defaults = chart.default_values()
            values = deep_merge(defaults, comp.values)

            # Dependency render
            chart._render_dependencies(values)

            # Chart render
            chart.render(values)

    return m


def _split_set_args(set_args: list[str]) -> tuple[list[str], list[str]]:
    """Split --set args into stack vs other.

    components.X.values.Y=Z → stack_set
    other → other_set
    """
    stack_set = []
    other_set = []
    for arg in set_args:
        if arg.startswith("components."):
            stack_set.append(arg)
        else:
            other_set.append(arg)
    return stack_set, other_set


def _apply_component_overrides(data: dict[str, Any], set_args: list[str]) -> None:
    """Apply --set in components.X.values.Y=Z format.

    Deep merges into the matching component's values
    without breaking the stack's components list.
    """
    from bow.chart.values import parse_set_values, deep_merge as dm

    components = data.get("components", [])
    if not isinstance(components, list):
        return

    # Component name → index mapping
    comp_by_name: dict[str, int] = {}
    for i, comp in enumerate(components):
        name = comp.get("name", comp.get("chart", ""))
        comp_by_name[name] = i

    for arg in set_args:
        # components.main-db.values.replicas=9
        # → parts: ["components", "main-db", "values", "replicas"]
        key, value = arg.split("=", 1)
        parts = key.split(".")

        if len(parts) < 4 or parts[0] != "components" or parts[2] != "values":
            continue

        comp_name = parts[1]
        value_key = ".".join(parts[3:])

        if comp_name not in comp_by_name:
            continue

        idx = comp_by_name[comp_name]
        comp = components[idx]

        # Values override
        override = parse_set_values([f"{value_key}={value}"])
        comp["values"] = dm(comp.get("values", {}), override)
