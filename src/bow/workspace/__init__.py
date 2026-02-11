"""bow.workspace — Workspace & lock management."""

from bow.workspace.lock import (
    LockSpec, parse_lock, write_lock,
    compute_checksum, check_drift, LockError,
)
from bow.workspace.stage import resolve_stages, resolve_value_files
from bow.workspace.resolver import (
    resolve_workspace, WorkspacePlan, WorkspaceError,
)

__all__ = [
    "LockSpec", "parse_lock", "write_lock",
    "compute_checksum", "check_drift", "LockError",
    "resolve_stages", "resolve_value_files",
    "resolve_workspace", "WorkspacePlan", "WorkspaceError",
]
