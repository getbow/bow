"""
bow.cli.template — bow template command.

Three modes:
  bow template <chart>              — Single chart render
  bow template -f stack.yaml        — Stack render
  bow template                      — Workspace (bow.lock)
  bow template --stage prod         — Workspace + stage overlay
"""

import sys
import click

from bow.chart.registry import get_chart


@click.command("template")
@click.argument("chart_name", required=False, default=None)
@click.option("-f", "--values", "value_files", multiple=True,
              help="Values or stack file (multiple allowed)")
@click.option("--set", "set_args", multiple=True,
              help="Value override (key=value)")
@click.option("-n", "--namespace", default=None,
              help="Kubernetes namespace")
@click.option("-o", "--output", default=None,
              help="Output file (default: stdout)")
@click.option("--stage", "stages", multiple=True,
              help="Stage overlay (values.<stage>.yaml)")
@click.option("-C", "--dir", "workspace_dir", default=None,
              help="Workspace directory (default: pwd)")
def template_cmd(chart_name, value_files, set_args, namespace, output,
                 stages, workspace_dir):
    """Render a chart, stack, or workspace as YAML."""
    # Mode detection
    if chart_name is not None:
        # Mode 1: Chart direct
        _template_chart(chart_name, value_files, set_args, namespace, output)
    elif value_files and not _has_lock(workspace_dir):
        # Mode 2: Stack direct (-f provided, no lock)
        _template_stack(value_files, set_args, namespace, output)
    else:
        # Mode 3: Workspace (bow.lock)
        _template_workspace(workspace_dir, stages, value_files, set_args,
                            namespace, output)


def _template_chart(chart_name, value_files, set_args, namespace, output):
    """Single chart render."""
    chart = get_chart(chart_name)
    if chart is None:
        click.echo(f"Error: Chart '{chart_name}' not found.", err=True)
        click.echo("Run 'bow list' to see available charts.", err=True)
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

    _output_yaml(m.to_yaml(), output)


def _template_stack(value_files, set_args, namespace, output):
    """Stack render."""
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

    _output_yaml(m.to_yaml(), output)


def _template_workspace(workspace_dir, stages, extra_files, set_args,
                        namespace, output):
    """Workspace render (bow.lock)."""
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

    if plan.has_drift:
        click.echo(
            f"⚠ Drift detected: files changed since last lock. "
            f"Run 'bow lock' to update checksum.",
            err=True,
        )

    if plan.is_stack:
        _template_stack(plan.files, plan.set_args, ns, output)
    else:
        chart = get_chart(plan.lock.chart)
        if chart is None:
            click.echo(
                f"Error: Chart '{plan.lock.chart}' not found. "
                f"Install: pip install bow-{plan.lock.chart}",
                err=True,
            )
            sys.exit(1)

        # Version check
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

        _output_yaml(m.to_yaml(), output)


def _output_yaml(yaml_str, output):
    if not yaml_str:
        click.echo("Warning: No resources produced.", err=True)
        return
    if output:
        with open(output, "w") as f:
            f.write(yaml_str)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(yaml_str)


def _has_lock(workspace_dir=None) -> bool:
    from pathlib import Path
    ws = Path(workspace_dir or ".").resolve()
    return (ws / "bow.lock").exists()
