"""
bow.chart.values — Values merge logic.

Value precedence (same as Helm):
  defaults.yaml (chart) → -f values.yaml → -f values2.yaml → --set key=val

Deep merge: nested dicts are merged, scalars are overridden.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts. Override wins.

    >>> deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 99}})
    {'a': {'b': 99, 'c': 2}}
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_values_file(path: str | Path) -> dict:
    """Read a YAML values file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Values file not found: {p}")
    with open(p) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def parse_set_values(set_args: list[str]) -> dict:
    """Convert --set key=value arguments to a nested dict.

    >>> parse_set_values(["replicas=3", "postgresql.storage=50Gi"])
    {'replicas': '3', 'postgresql': {'storage': '50Gi'}}
    """
    result: dict = {}
    for arg in set_args:
        if "=" not in arg:
            raise ValueError(f"Invalid --set format: '{arg}' (expected key=value)")
        key, value = arg.split("=", 1)
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        # Basit type coercion
        current[parts[-1]] = _coerce_value(value)
    return result


def _coerce_value(value: str) -> Any:
    """Convert a string value to the appropriate Python type.

    >>> _coerce_value("3")
    3
    >>> _coerce_value("true")
    True
    >>> _coerce_value("50Gi")
    '50Gi'
    """
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null" or value.lower() == "none":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def merge_all_values(
    defaults: dict,
    value_files: list[str | Path],
    set_args: list[str],
) -> dict:
    """Merge all value sources.

    Precedence (low to high):
      defaults → value_files (in order) → set_args
    """
    result = copy.deepcopy(defaults)
    for vf in value_files:
        file_values = load_values_file(vf)
        result = deep_merge(result, file_values)
    if set_args:
        set_values = parse_set_values(set_args)
        result = deep_merge(result, set_values)
    return result
