"""
bow.cli.status_cmd — bow status command.

Shows workspace status: lock info, stage, drift.
"""

import sys
import click

from bow.workspace.lock import parse_lock, check_drift, compute_checksum, LockError
from bow.workspace.stage import resolve_stages


@click.command("status")
@click.option("--stage", "stages", multiple=True,
              help="Show stage overlay")
@click.option("-C", "--dir", "workspace_dir", default=None,
              help="Workspace directory (default: pwd)")
def status_cmd(stages, workspace_dir):
    """Show workspace status."""
    from pathlib import Path

    ws = Path(workspace_dir or ".").resolve()
    lock_path = ws / "bow.lock"

    if not lock_path.exists():
        click.echo(f"No bow.lock found in {ws}")
        click.echo("Run 'bow lock --init <chart>' to initialize.")
        return

    try:
        lock = parse_lock(lock_path)
    except LockError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Lock info
    click.echo(f"Workspace:  {ws}")
    if lock.chart:
        click.echo(f"Chart:      {lock.chart}")
    if lock.stack:
        click.echo(f"Stack:      {lock.stack}")
    if lock.version:
        click.echo(f"Version:    {lock.version}")
    if lock.namespace:
        click.echo(f"Namespace:  {lock.namespace}")

    # Stage
    resolved = resolve_stages(stages)
    if resolved:
        click.echo(f"Stage:      {', '.join(resolved)}")

    # Values files
    click.echo(f"\nFiles:")
    for f in sorted(ws.glob("values*.yaml")):
        click.echo(f"  {f.name}")
    if (ws / "stack.yaml").exists():
        click.echo(f"  stack.yaml")

    # Drift check
    click.echo()
    if lock.checksum:
        has_drift = check_drift(ws, lock)
        current = compute_checksum(ws)
        if has_drift:
            click.echo(f"⚠ DRIFT DETECTED")
            click.echo(f"  locked:  {lock.checksum}")
            click.echo(f"  current: {current}")
            click.echo(f"  Run 'bow lock' to update.")
        else:
            click.echo(f"✓ No drift. Checksum: {lock.checksum[:30]}...")
    else:
        click.echo("No checksum in lock file. Run 'bow lock' to set one.")

    # Version check
    if lock.chart:
        from bow.chart.registry import get_chart
        chart = get_chart(lock.chart)
        if chart is None:
            click.echo(f"\n⚠ Chart '{lock.chart}' not installed!")
        elif lock.version and chart.version != lock.version:
            click.echo(
                f"\n⚠ Version mismatch: lock={lock.version} "
                f"installed={chart.version}"
            )
