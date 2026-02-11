"""
bow.cli.lock_cmd — bow lock command.

Updates the checksum of the bow.lock file in the workspace.
Can also create a new lock file.

  bow lock                       — Update existing lock's checksum
  bow lock --init postgresql     — Create a new lock file
  bow lock --init --stack        — Create a new lock for a stack
"""

import sys
import click

from bow.workspace.lock import (
    LockSpec, parse_lock, write_lock, compute_checksum, LockError,
)
from bow.chart.registry import get_chart


@click.command("lock")
@click.option("--init", "init_chart", default=None,
              help="Create a new lock file (chart name)")
@click.option("--stack", is_flag=True, default=False,
              help="Create lock in stack mode (with --init)")
@click.option("-n", "--namespace", default=None,
              help="Kubernetes namespace")
@click.option("--create-namespace", is_flag=True, default=False,
              help="Write create-namespace flag to lock")
@click.option("-C", "--dir", "workspace_dir", default=None,
              help="Workspace directory (default: pwd)")
def lock_cmd(init_chart, stack, namespace, create_namespace, workspace_dir):
    """Create or update a lock file."""
    from pathlib import Path

    ws = Path(workspace_dir or ".").resolve()
    lock_path = ws / "bow.lock"

    if init_chart or stack:
        _init_lock(lock_path, init_chart, stack, namespace,
                   create_namespace, ws)
    else:
        _update_checksum(lock_path, ws)


def _init_lock(lock_path, chart_name, is_stack, namespace,
               create_namespace, ws):
    """Create a new bow.lock."""
    from pathlib import Path

    if lock_path.exists():
        if not click.confirm(f"Lock file already exists: {lock_path}\nOverwrite?"):
            return

    lock = LockSpec(namespace=namespace, create_namespace=create_namespace)

    if is_stack:
        lock.stack = "stack.yaml"
        click.echo("Initialized stack lock.", err=True)
    elif chart_name:
        chart = get_chart(chart_name)
        if chart:
            lock.chart = chart_name
            lock.version = chart.version
            click.echo(f"Initialized lock: {chart_name}@{chart.version}", err=True)
        else:
            lock.chart = chart_name
            click.echo(
                f"Warning: Chart '{chart_name}' not installed. "
                f"Lock created without version.",
                err=True,
            )
    else:
        click.echo("Error: --init requires a chart name or --stack.", err=True)
        return

    # Checksum
    lock.checksum = compute_checksum(ws)

    write_lock(lock, lock_path)
    click.echo(f"Lock written: {lock_path}", err=True)
    click.echo(f"Checksum: {lock.checksum}", err=True)


def _update_checksum(lock_path, ws):
    """Update the existing lock's checksum."""
    try:
        lock = parse_lock(lock_path)
    except LockError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Run 'bow lock --init <chart>' to create a lock file.", err=True)
        sys.exit(1)

    old_checksum = lock.checksum
    new_checksum = compute_checksum(ws)

    if old_checksum == new_checksum:
        click.echo("Lock is up to date. No changes detected.", err=True)
        return

    lock.checksum = new_checksum
    write_lock(lock, lock_path)

    click.echo(f"Checksum updated:", err=True)
    click.echo(f"  old: {old_checksum}", err=True)
    click.echo(f"  new: {new_checksum}", err=True)
