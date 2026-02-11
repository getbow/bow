"""
bow.stack.parser — Stack YAML parser.

stack.yaml format:

    apiVersion: bow.io/v1
    kind: Stack
    metadata:
      name: my-project
      namespace: my-project
    components:
      - chart: postgresql
        name: main-db
        values:
          storage: 50Gi
      - chart: redis
        name: cache

Parser reads the stack file, validates it, and
converts it to a StackSpec object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ComponentSpec:
    """A single stack component."""
    chart: str
    name: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class StackSpec:
    """Parsed stack definition."""
    name: str
    namespace: str | None = None
    components: list[ComponentSpec] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class StackParseError(Exception):
    """Stack parse error."""
    pass


def parse_stack_file(path: str | Path) -> StackSpec:
    """Parse a stack.yaml file.

    Args:
        path: Path to stack.yaml

    Returns:
        StackSpec object

    Raises:
        StackParseError: Format error
        FileNotFoundError: File not found
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Stack file not found: {p}")

    with open(p) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise StackParseError(f"Stack file must be a YAML mapping, got {type(data).__name__}")

    return parse_stack_dict(data)


def parse_stack_dict(data: dict[str, Any]) -> StackSpec:
    """Create a StackSpec from a dict.

    Args:
        data: stack.yaml content (as dict)

    Returns:
        StackSpec object
    """
    # Validate apiVersion
    api_version = data.get("apiVersion", "")
    if api_version and api_version != "bow.io/v1":
        raise StackParseError(
            f"Unsupported apiVersion: '{api_version}'. Expected 'bow.io/v1'"
        )

    # Validate kind
    kind = data.get("kind", "")
    if kind and kind != "Stack":
        raise StackParseError(
            f"Unsupported kind: '{kind}'. Expected 'Stack'"
        )

    # Metadata
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise StackParseError("metadata must be a mapping")

    name = metadata.get("name", "")
    if not name:
        raise StackParseError("metadata.name is required")

    namespace = metadata.get("namespace")

    # Components
    components_raw = data.get("components", [])
    if not isinstance(components_raw, list):
        raise StackParseError("components must be a list")

    components: list[ComponentSpec] = []
    seen_names: set[str] = set()

    for i, comp in enumerate(components_raw):
        if not isinstance(comp, dict):
            raise StackParseError(f"components[{i}] must be a mapping")

        chart = comp.get("chart")
        if not chart:
            raise StackParseError(f"components[{i}].chart is required")

        comp_name = comp.get("name", chart)

        if comp_name in seen_names:
            raise StackParseError(
                f"Duplicate component name: '{comp_name}'. "
                f"Use 'name' field to distinguish multiple instances of the same chart."
            )
        seen_names.add(comp_name)

        values = comp.get("values", {})
        if not isinstance(values, dict):
            raise StackParseError(f"components[{i}].values must be a mapping")

        components.append(ComponentSpec(
            chart=chart,
            name=comp_name,
            values=values,
        ))

    return StackSpec(
        name=name,
        namespace=namespace,
        components=components,
        raw=data,
    )
