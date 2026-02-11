"""
bow.workspace.stage — Stage management.

Stage resolution priority:
    --stage flag > KUBRIC_STAGE env var > None (base only)

A stage maps to an overlay file:
    --stage prod → values.prod.yaml
    --stage staging → values.staging.yaml

Multiple stages are supported (composition):
    --stage prod --stage eu-west → values.prod.yaml + values.eu-west.yaml
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_stages(
    flag_stages: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Resolve the stage list.

    Priority: flag > env var > empty

    Args:
        flag_stages: --stage values from CLI

    Returns:
        Stage name list (may be empty)
    """
    if flag_stages:
        return list(flag_stages)

    env_stage = os.environ.get("KUBRIC_STAGE", "").strip()
    if env_stage:
        # Comma-separated: KUBRIC_STAGE=prod,eu-west
        return [s.strip() for s in env_stage.split(",") if s.strip()]

    return []


def resolve_value_files(
    workspace_dir: str | Path,
    stages: list[str],
    extra_files: list[str] | None = None,
) -> list[str]:
    """Resolve values files from workspace directory based on stage.

    File order (low to high precedence):
    1. values.yaml (base — always included)
    2. values.<stage>.yaml (in stage order)
    3. Extra -f files

    Args:
        workspace_dir: Workspace directory
        stages: Stage names
        extra_files: Additional -f files

    Returns:
        List of file paths (existing ones only)
    """
    ws = Path(workspace_dir)
    files: list[str] = []

    # 1. Base values
    base = ws / "values.yaml"
    if base.exists():
        files.append(str(base))

    # 2. Stage overlays
    for stage in stages:
        stage_file = ws / f"values.{stage}.yaml"
        if stage_file.exists():
            files.append(str(stage_file))
        else:
            # Stage file not found — warning, not error
            import click
            click.echo(
                f"Warning: Stage file not found: {stage_file}",
                err=True,
            )

    # 3. Extra files
    if extra_files:
        files.extend(extra_files)

    return files


def resolve_stack_files(
    workspace_dir: str | Path,
    stages: list[str],
    extra_files: list[str] | None = None,
) -> list[str]:
    """Resolve file list for a stack workspace.

    File order:
    1. stack.yaml (base — required)
    2. values.yaml (if exists)
    3. values.<stage>.yaml (in stage order)
    4. Extra -f files

    Returns:
        List of file paths
    """
    ws = Path(workspace_dir)
    files: list[str] = []

    # 1. Stack file
    stack_file = ws / "stack.yaml"
    if stack_file.exists():
        files.append(str(stack_file))

    # 2-4. Values (stage dahil)
    value_files = resolve_value_files(ws, stages, extra_files)
    files.extend(value_files)

    return files
