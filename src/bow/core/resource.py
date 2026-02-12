"""
bow.core.resource — Base Resource class.

Common behaviors for all Kubernetes resources:
- Context manager (with block)
- Parent-child relationship (via stack)
- Tracking labels (bow.io/*)
- YAML render
"""

from __future__ import annotations

from typing import Any

from bow.core.stack import _current, _push, _pop, _collected


# Bow tracking labels
_TRACKING_LABELS: dict[str, str] = {}


def set_tracking(chart: str | None = None, version: str | None = None,
                 stack: str | None = None) -> None:
    """Set global tracking labels. Called by the CLI."""
    _TRACKING_LABELS.clear()
    _TRACKING_LABELS["bow.io/managed-by"] = "bow"
    if chart:
        _TRACKING_LABELS["bow.io/chart"] = chart
    if version:
        _TRACKING_LABELS["bow.io/version"] = version
    if stack:
        _TRACKING_LABELS["bow.io/stack"] = stack


class Resource:
    """Base class for all K8s resources.

    Used with the `with` block. Pushes onto the stack in __enter__,
    pops in __exit__. If there is no parent, it is registered as a
    top-level resource in the manifest's collected list.
    """

    _kind: str = ""
    _api_version: str = "v1"

    def __init__(self, name: str, **kwargs: Any):
        self.name = name
        self.metadata: dict[str, Any] = {"name": name}
        self.children: list[Any] = []

        # Chart-level flags 
        self.enabled = kwargs.pop("enabled", True)

        # Labels
        labels = dict(kwargs.pop("labels", {}) or {})
        labels.update(_TRACKING_LABELS)
        if labels:
            self.metadata["labels"] = labels

        # Annotations
        annotations = kwargs.pop("annotations", None)
        if annotations:
            self.metadata["annotations"] = annotations

        # Namespace
        namespace = kwargs.pop("namespace", None)
        if namespace:
            self.metadata["namespace"] = namespace

        self.props = kwargs

        # Attach to parent or register as top-level
        parent = _current()
        if parent is not None:
            parent._adopt(self)
        else:
            _collected().append(self)

    def _adopt(self, child: Any) -> None:
        """Accept a child resource. Subclasses may override."""
        self.children.append(child)

    def __enter__(self):
        _push(self)
        return self

    def __exit__(self, *exc: Any) -> bool:
        _pop()
        return False

    def render(self) -> dict[str, Any]:
        """Produce a single K8s resource dict."""
        raise NotImplementedError(f"{self.__class__.__name__}.render()")

    def render_all(self) -> list[dict[str, Any]]:
        """Return this resource + related resources (Service, PVC, etc.)."""
        return [self.render()]
