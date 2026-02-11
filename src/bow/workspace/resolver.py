"""
bow.workspace.resolver — Workspace resolver.

Takes a directory, reads bow.lock, resolves stages,
collects files, and returns a deploy/template-ready
WorkspacePlan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bow.workspace.lock import (
    LockSpec, parse_lock, compute_checksum, check_drift, LockError,
)
from bow.workspace.stage import (
    resolve_stages, resolve_value_files, resolve_stack_files,
)


@dataclass
class WorkspacePlan:
    """Resolved workspace deploy plan."""
    workspace_dir: Path
    lock: LockSpec
    stages: list[str]
    files: list[str]           # files to pass to deploy/template
    set_args: list[str] = field(default_factory=list)
    has_drift: bool = False    # whether checksum has changed

    @property
    def namespace(self) -> str | None:
        return self.lock.namespace

    @property
    def is_stack(self) -> bool:
        return self.lock.is_stack


class WorkspaceError(Exception):
    """Workspace resolution error."""
    pass


def resolve_workspace(
    workspace_dir: str | Path | None = None,
    stage_flags: list[str] | tuple[str, ...] | None = None,
    extra_files: list[str] | None = None,
    set_args: list[str] | None = None,
) -> WorkspacePlan:
    """Resolve workspace directory and build deploy plan.

    Args:
        workspace_dir: Workspace directory (None = cwd)
        stage_flags: --stage flag values
        extra_files: Additional -f files
        set_args: --set values

    Returns:
        WorkspacePlan

    Raises:
        WorkspaceError: Resolution error
    """
    ws = Path(workspace_dir or ".").resolve()

    if not ws.is_dir():
        raise WorkspaceError(f"Not a directory: {ws}")

    # 1. Read lock file
    lock_path = ws / "bow.lock"
    try:
        lock = parse_lock(lock_path)
    except LockError as e:
        raise WorkspaceError(str(e)) from e

    # 2. Resolve stages
    stages = resolve_stages(stage_flags)

    # 3. Collect files
    if lock.is_stack:
        files = resolve_stack_files(ws, stages, extra_files)
        # stack.yaml required
        stack_file = ws / "stack.yaml"
        if not stack_file.exists():
            # Lock has stack reference but file not found
            stack_name = lock.stack or "stack.yaml"
            stack_file = ws / stack_name
            if not stack_file.exists():
                raise WorkspaceError(
                    f"Stack file not found: {stack_file}"
                )
    else:
        files = resolve_value_files(ws, stages, extra_files)

    # 4. Drift check
    has_drift = check_drift(ws, lock)

    return WorkspacePlan(
        workspace_dir=ws,
        lock=lock,
        stages=stages,
        files=files,
        set_args=list(set_args or []),
        has_drift=has_drift,
    )
