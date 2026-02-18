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
    """String değeri uygun Python tipine çevir.

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
) -> Values:
    """Merge all value sources and return a Values object.

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
    return Values(result)


class Values:
    """Dot-notation access wrapper over a dict.

    Provides clean attribute-style access to nested config::

        v.service.port          # instead of values["service"]["port"]
        v.resources.cpu         # nested access
        v.replicas              # scalar

    If a key is missing, raises AttributeError with a clear message
    pointing to the missing key path (means defaults.yaml is incomplete).

    The underlying dict is always accessible via ``v._data``.
    Dict-style access (v["key"]) and iteration also work.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, key: str) -> Any:
        try:
            val = self._data[key]
        except KeyError:
            raise AttributeError(
                f"Value '{key}' not found. "
                f"Add it to defaults.yaml or pass via -f / --set"
            ) from None
        if isinstance(val, dict):
            return Values(val)
        return val

    def __getitem__(self, key: str) -> Any:
        val = self._data[key]
        if isinstance(val, dict):
            return Values(val)
        return val

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __repr__(self) -> str:
        return f"Values({self._data!r})"

    def __bool__(self) -> bool:
        return bool(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get with fallback."""
        val = self._data.get(key, default)
        if isinstance(val, dict):
            return Values(val)
        return val

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def to_dict(self) -> dict[str, Any]:
        """Return the underlying raw dict."""
        return self._data
