"""
bow.stack.refs — Component reference resolver.

Stack components can reference each other using the
${component_name.field} syntax. Currently supported fields:

  ${component_name.host}  → component's Service name
  ${component_name.port}  → component's first Service port
  ${component_name.name}  → component name

Example:
    components:
      - chart: postgresql
        name: db
        values:
          database: myapp

      - chart: myapp
        name: api
        values:
          database_url: "postgresql://${db.host}:${db.port}/${db.values.database}"
"""

from __future__ import annotations

import re
from typing import Any

from bow.stack.parser import ComponentSpec

# ${component_name.field} or ${component_name.values.key}
_REF_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_.]+)\}")


def resolve_refs(
    components: list[ComponentSpec],
) -> list[ComponentSpec]:
    """Resolve all references in all components.

    Args:
        components: ComponentSpec list

    Returns:
        New ComponentSpec list with resolved references
    """
    # Component lookup tablosu
    lookup: dict[str, ComponentSpec] = {c.name: c for c in components}

    resolved: list[ComponentSpec] = []
    for comp in components:
        new_values = _resolve_dict(comp.values, lookup)
        resolved.append(ComponentSpec(
            chart=comp.chart,
            name=comp.name,
            values=new_values,
        ))
    return resolved


def _resolve_dict(data: dict, lookup: dict[str, ComponentSpec]) -> dict:
    """Resolve all references in string values within a dict."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = _resolve_string(value, lookup)
        elif isinstance(value, dict):
            result[key] = _resolve_dict(value, lookup)
        elif isinstance(value, list):
            result[key] = _resolve_list(value, lookup)
        else:
            result[key] = value
    return result


def _resolve_list(data: list, lookup: dict[str, ComponentSpec]) -> list:
    """Resolve references within a list."""
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(_resolve_string(item, lookup))
        elif isinstance(item, dict):
            result.append(_resolve_dict(item, lookup))
        elif isinstance(item, list):
            result.append(_resolve_list(item, lookup))
        else:
            result.append(item)
    return result


def _resolve_string(value: str, lookup: dict[str, ComponentSpec]) -> str:
    """Resolve ${ref} patterns within a string."""

    def replacer(match: re.Match) -> str:
        comp_name = match.group(1)
        field_path = match.group(2)

        if comp_name not in lookup:
            raise RefError(
                f"Unknown component reference: '${{{comp_name}.{field_path}}}'. "
                f"Available components: {list(lookup.keys())}"
            )

        comp = lookup[comp_name]
        return _get_field(comp, field_path)

    return _REF_PATTERN.sub(replacer, value)


def _get_field(comp: ComponentSpec, field_path: str) -> str:
    """Get a field value from a component.

    Supported fields:
      host    → component name (used as Service name)
      port    → chart's default port (from values)
      name    → component name
      values.X → nested lookup from values dict
    """
    parts = field_path.split(".", 1)
    field = parts[0]

    if field == "host":
        # Service name = component name
        return comp.name
    elif field == "name":
        return comp.name
    elif field == "port":
        # Values'dan service.port veya ilk bilinen port
        svc = comp.values.get("service", {})
        if isinstance(svc, dict) and "port" in svc:
            return str(svc["port"])
        # Chart-specific default ports
        default_ports = {
            "postgresql": "5432",
            "redis": "6379",
            "mysql": "3306",
            "mongodb": "27017",
        }
        return default_ports.get(comp.chart, "80")
    elif field == "values" and len(parts) > 1:
        # values.database → comp.values["database"]
        return _get_nested_str(comp.values, parts[1])
    else:
        raise RefError(
            f"Unknown field '{field_path}' for component '{comp.name}'. "
            f"Supported: host, port, name, values.<key>"
        )


def _get_nested_str(data: dict, path: str) -> str:
    """Get a value from a nested dict using a dot-separated path."""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise RefError(f"Key not found in values: '{path}'")
    return str(current)


class RefError(Exception):
    """Reference resolution error."""
    pass
