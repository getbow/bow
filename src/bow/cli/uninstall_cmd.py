"""
bow.cli.uninstall_cmd — Remove a chart from the active env.

  bow uninstall postgresql
  bow uninstall postgresql redis
  bow uninstall postgresql --yes
"""

import sys
import subprocess
import click


@click.command("uninstall")
@click.argument("charts", nargs=-1, required=True)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
def uninstall_cmd(charts, yes):
    """Remove chart(s) from the active env."""
    from bow.oci.env import get_env, EnvError

    try:
        env = get_env()
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not env.exists():
        click.echo(f"Error: Env '{env.name}' not initialized.", err=True)
        sys.exit(1)

    # chart name → pip package name (postgresql → bow-postgresql)
    packages = [f"{name}" for name in charts]

    if not yes:
        click.echo(f"Will uninstall from env '{env.name}':")
        for name, pkg in zip(charts, packages):
            click.echo(f"  {name} ({pkg})")
        if not click.confirm("Proceed?"):
            return

    pip = env.pip_path
    result = subprocess.run(
        [str(pip), "uninstall", "-y", *packages],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        click.echo(f"Error:\n{result.stderr}", err=True)
        sys.exit(1)

    for name in charts:
        click.echo(f"✓ {name} uninstalled from env '{env.name}'", err=True)