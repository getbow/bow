"""
bow.workspace.lock — bow.lock file management.

bow.lock format:

    apiVersion: bow.io/v1
    kind: Lock
    chart: postgresql            # or stack: stack.yaml
    version: "16.4.0"
    namespace: t1-postgresql
    checksum: sha256:abc123...   # hash of values + stack files

Checksum: Combined SHA256 hash of values.yaml + values.*.yaml + stack.yaml
files. Used for change detection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LockSpec:
    """Parsed bow.lock."""
    chart: str | None = None
    stack: str | None = None
    version: str | None = None
    namespace: str | None = None
    checksum: str | None = None
    create_namespace: bool = False

    @property
    def is_stack(self) -> bool:
        return self.stack is not None

    @property
    def display_name(self) -> str:
        if self.chart:
            label = self.chart
            if self.version:
                label += f"@{self.version}"
            return label
        return self.stack or "unknown"


class LockError(Exception):
    """Lock file error."""
    pass


def parse_lock(path: str | Path) -> LockSpec:
    """Parse a bow.lock file."""
    p = Path(path)
    if not p.exists():
        raise LockError(f"Lock file not found: {p}")

    with open(p) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise LockError(f"Lock file must be a YAML mapping: {p}")

    chart = data.get("chart")
    stack = data.get("stack")

    if not chart and not stack:
        raise LockError("Lock file must specify either 'chart' or 'stack'")
    if chart and stack:
        raise LockError("Lock file cannot specify both 'chart' and 'stack'")

    return LockSpec(
        chart=chart,
        stack=stack,
        version=data.get("version"),
        namespace=data.get("namespace"),
        checksum=data.get("checksum"),
        create_namespace=data.get("create_namespace", False),
    )


def write_lock(lock: LockSpec, path: str | Path) -> None:
    """Write a bow.lock file."""
    data: dict[str, Any] = {
        "apiVersion": "bow.io/v1",
        "kind": "Lock",
    }

    if lock.chart:
        data["chart"] = lock.chart
    if lock.stack:
        data["stack"] = lock.stack
    if lock.version:
        data["version"] = lock.version
    if lock.namespace:
        data["namespace"] = lock.namespace
    if lock.create_namespace:
        data["create_namespace"] = True
    if lock.checksum:
        data["checksum"] = lock.checksum

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def compute_checksum(workspace_dir: str | Path) -> str:
    """Compute the checksum of all yaml files in the workspace directory.

    Included files:
    - values.yaml, values.*.yaml
    - stack.yaml
    - bow.lock is NOT included (checksum doesn't hash itself)

    Returns:
        Hash string in "sha256:<hex>" format
    """
    ws = Path(workspace_dir)
    hasher = hashlib.sha256()

    # Read files in order (deterministic)
    files_to_hash: list[Path] = []

    # stack.yaml
    stack_file = ws / "stack.yaml"
    if stack_file.exists():
        files_to_hash.append(stack_file)

    # values.yaml ve values.*.yaml
    values_main = ws / "values.yaml"
    if values_main.exists():
        files_to_hash.append(values_main)

    for vf in sorted(ws.glob("values.*.yaml")):
        files_to_hash.append(vf)

    for fp in files_to_hash:
        # Include filename in hash (rename detection)
        hasher.update(fp.name.encode())
        hasher.update(fp.read_bytes())

    return f"sha256:{hasher.hexdigest()}"


def check_drift(workspace_dir: str | Path, lock: LockSpec) -> bool:
    """Check whether files have changed in the workspace.

    Returns:
        True = drift detected (files changed), False = clean
    """
    if not lock.checksum:
        return False  # Skip drift check if no checksum

    current = compute_checksum(workspace_dir)
    return current != lock.checksum
