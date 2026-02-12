"""
bow.core.manifest — Resource collector.

Works like Tagflow's document() function.
`with manifest() as m:` collects all top-level
resources inside the block and renders them as YAML.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import yaml

from bow.core.stack import _collected, _set_collected, _reset


class Manifest:
    """Converts collected resources to YAML."""

    def __init__(self, resources: list):
        self._resources = resources

    @property
    def resources(self) -> list:
        return list(self._resources)

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return all resources as a list of dicts."""
        docs: list[dict[str, Any]] = []
        for r in self._resources:
            for doc in r.render_all():
                if doc is not None:
                    docs.append(doc)
        return docs

    def to_yaml(self) -> str:
        """Produce a multi-document YAML string."""
        docs = self.to_dicts()
        if not docs:
            return ""
        parts: list[str] = []
        for doc in docs:
            parts.append(yaml.dump(
                doc,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            ))
        return "---\n".join(parts)


@contextmanager
def manifest():
    """Resource collector context manager.

    Collects all top-level resources inside the block::

        with manifest() as m:
            with Deployment("nginx"):
                with Container("nginx", image="nginx:latest"):
                    Port(80)
                Service(port=80)

            print(m.to_yaml())
    """
    old = list(_collected())
    resources: list = []
    _set_collected(resources)

    m = Manifest(resources)
    try:
        yield m
    finally:
        _set_collected(old)
