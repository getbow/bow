"""
bow.cli.up — bow up command.

Three modes:
  bow up postgresql --set ...       — Single chart deploy
  bow up -f stack.yaml              — Stack deploy
  bow up                            — Workspace (bow.lock)
  bow up --stage prod               — Workspace + stage overlay
"""

import sys
import subprocess
import click

from bow.chart.registry import get_chart


@click.command("up")
@click.argument("chart_name", required=False, default=None)
@click.option("-f", "--values", "value_files", multiple=True,
              help="Values or stack file (multiple allowed)")
@click.option("--set", "set_args", multiple=True,
              help="Value override (key=value)")
@click.option("-n", "--namespace", default=None,
              help="Kubernetes namespace")
@click.option("--create-namespace", is_flag=True, default=False,
              help="Create namespace if it doesn't exist")
@click.option("--dry-run", is_flag=True, default=False,
              help="kubectl apply --dry-run=client")
@click.option("--stage", "stages", multiple=True,
              help="Stage overlay (values.<stage>.yaml)")
@click.option("-C", "--dir", "workspace_dir", default=None,
              help="Workspace directory (default: pwd)")
def up_cmd(chart_name, value_files, set_args, namespace, create_namespace,
           dry_run, stages, workspace_dir):
    """Deploy a chart, stack, or workspace."""
    if chart_name is not None:
        _up_chart(chart_name, value_files, set_args, namespace,
                  create_namespace, dry_run)
    elif value_files and not _has_lock(workspace_dir):
        _up_stack(value_files, set_args, namespace, create_namespace, dry_run)
    else:
        _up_workspace(workspace_dir, stages, value_files, set_args,
                      namespace, create_namespace, dry_run)


def _up_chart(chart_name, value_files, set_args, namespace,
              create_namespace, dry_run):
    """Single chart deploy."""
    chart = get_chart(chart_name)
    if chart is None:
        click.echo(f"Error: Chart '{chart_name}' not found.", err=True)
        sys.exit(1)

    try:
        m = chart.template(
            value_files=list(value_files),
            set_args=list(set_args),
            namespace=namespace,
        )
    except Exception as e:
        click.echo(f"Error rendering chart: {e}", err=True)
        sys.exit(1)

    yaml_output = m.to_yaml()
    if not yaml_output:
        click.echo("Warning: Chart produced no resources.", err=True)
        return

    label = f"{chart.name}@{chart.version}"
    _kubectl_apply(yaml_output, namespace, create_namespace, dry_run, label)


def _up_stack(value_files, set_args, namespace, create_namespace, dry_run):
    """Stack deploy."""
    from bow.stack.engine import render_stack, StackError

    try:
        m = render_stack(
            file_paths=list(value_files),
            set_args=list(set_args),
            namespace=namespace,
        )
    except (FileNotFoundError, StackError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    yaml_output = m.to_yaml()
    if not yaml_output:
        click.echo("Warning: Stack produced no resources.", err=True)
        return

    _kubectl_apply(yaml_output, namespace, create_namespace, dry_run, "stack")


def _up_workspace(workspace_dir, stages, extra_files, set_args,
                  namespace, create_namespace, dry_run):
    """Workspace deploy (bow.lock)."""
    from bow.workspace.resolver import resolve_workspace, WorkspaceError

    try:
        plan = resolve_workspace(
            workspace_dir=workspace_dir,
            stage_flags=stages,
            extra_files=list(extra_files) if extra_files else None,
            set_args=list(set_args) if set_args else None,
        )
    except WorkspaceError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    ns = namespace or plan.namespace
    should_create_ns = create_namespace or plan.lock.create_namespace

    if plan.has_drift:
        click.echo(
            f"⚠ Drift detected: files changed since last lock. "
            f"Run 'bow lock' to update checksum.",
            err=True,
        )

    if plan.stages:
        click.echo(f"Stage: {', '.join(plan.stages)}", err=True)

    if plan.is_stack:
        from bow.stack.engine import render_stack, StackError
        try:
            m = render_stack(
                file_paths=plan.files,
                set_args=plan.set_args,
                namespace=ns,
            )
        except (FileNotFoundError, StackError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        yaml_output = m.to_yaml()
        label = f"stack ({plan.lock.display_name})"
    else:
        chart = get_chart(plan.lock.chart)
        if chart is None:
            click.echo(
                f"Error: Chart '{plan.lock.chart}' not found. "
                f"Install: pip install bow-{plan.lock.chart}",
                err=True,
            )
            sys.exit(1)

        if plan.lock.version and chart.version != plan.lock.version:
            click.echo(
                f"⚠ Version mismatch: lock={plan.lock.version} "
                f"installed={chart.version}",
                err=True,
            )

        try:
            m = chart.template(
                value_files=plan.files,
                set_args=plan.set_args,
                namespace=ns,
            )
        except Exception as e:
            click.echo(f"Error rendering chart: {e}", err=True)
            sys.exit(1)

        yaml_output = m.to_yaml()
        label = plan.lock.display_name

    if not yaml_output:
        click.echo("Warning: No resources produced.", err=True)
        return

    _kubectl_apply(yaml_output, ns, should_create_ns, dry_run, label)


def _kubectl_apply(yaml_output, namespace, create_namespace, dry_run, label):
    """Run kubectl apply -f -."""
    if create_namespace and namespace:
        _ensure_namespace(namespace, dry_run)

    cmd = ["kubectl", "apply", "-f", "-"]
    if namespace:
        cmd.extend(["-n", namespace])
    if dry_run:
        cmd.append("--dry-run=client")

    click.echo(f"Deploying {label}...", err=True)

    try:
        result = subprocess.run(cmd, input=yaml_output, text=True,
                                capture_output=True)
    except FileNotFoundError:
        click.echo("Error: kubectl not found.", err=True)
        sys.exit(1)

    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)
    if result.returncode != 0:
        sys.exit(result.returncode)

    click.echo(f"✓ {label} deployed successfully.", err=True)


def _ensure_namespace(namespace, dry_run=False):
    cmd = ["kubectl", "create", "namespace", namespace,
           "--dry-run=client" if dry_run else "--dry-run=none",
           "-o", "yaml"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        apply_cmd = ["kubectl", "apply", "-f", "-"]
        if dry_run:
            apply_cmd.append("--dry-run=client")
        subprocess.run(apply_cmd, input=result.stdout, text=True,
                       capture_output=True)


def _has_lock(workspace_dir=None) -> bool:
    from pathlib import Path
    ws = Path(workspace_dir or ".").resolve()
    return (ws / "bow.lock").exists()
