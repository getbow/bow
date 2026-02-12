"""
bow.cli.install_cmd — Install a chart from a local directory.

Installs a chart directly into the active env's venv
without pushing to a registry first. Useful during
chart development.

  bow install ./charts/bow-postgresql
  bow install ./charts/bow-postgresql --editable
  bow install . -e
"""

import sys
import click


@click.command("install")
@click.argument("chart_dir", default=".")
@click.option("-e", "--editable", is_flag=True,
              help="Editable install (changes reflect immediately)")
def install_cmd(chart_dir, editable):
    """Install a local chart into the active env."""
    from pathlib import Path
    from bow.oci.env import get_env, EnvError

    chart_path = Path(chart_dir).resolve()

    # Validate chart dir
    has_pyproject = (chart_path / "pyproject.toml").exists()
    has_chart_json = (chart_path / "chart.json").exists()

    if not has_pyproject and not has_chart_json:
        click.echo(
            f"Error: Not a chart directory: {chart_path}\n"
            f"Expected pyproject.toml or chart.json",
            err=True,
        )
        sys.exit(1)

    try:
        env = get_env()
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not env.exists():
        click.echo(
            f"Error: Env '{env.name}' not initialized.\n"
            f"Run: bow env create {env.name}",
            err=True,
        )
        sys.exit(1)

    pip = env.pip_path
    if not pip.exists():
        click.echo(f"Error: pip not found in env '{env.name}'", err=True)
        sys.exit(1)

    # Build pip command
    cmd = [str(pip), "install"]
    if editable:
        cmd.extend(["-e", str(chart_path)])
    else:
        cmd.append(str(chart_path))

    import subprocess
    click.echo(
        f"Installing {chart_path.name} into env '{env.name}'"
        f"{' (editable)' if editable else ''}...",
        err=True,
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        click.echo(f"Error: pip install failed:\n{result.stderr}", err=True)
        sys.exit(1)

    click.echo(f"✓ {chart_path.name} installed in env '{env.name}'", err=True)