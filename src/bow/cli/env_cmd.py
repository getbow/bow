"""
bow.cli.env_cmd — bow env command.

  bow env create prod
  bow env use prod
  bow env list
  bow env delete staging
"""

import sys
import click


@click.group("env")
def env_cmd():
    """Environment management."""
    pass


@env_cmd.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Environment description")
def env_create(name, description):
    """Create a new environment."""
    from bow.oci.env import create_env, EnvError

    try:
        info = create_env(name, description=description)
        click.echo(f"✓ Environment '{name}' created at {info.path}")
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@env_cmd.command("use")
@click.argument("name")
def env_use(name):
    """Switch the active environment."""
    from bow.oci.env import use_env, EnvError

    try:
        use_env(name)
        click.echo(f"✓ Active environment: {name}")
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@env_cmd.command("list")
def env_list():
    """List all environments."""
    from bow.oci.env import list_envs, resolve_active_env

    envs = list_envs()
    active = resolve_active_env()

    if not envs:
        click.echo("No environments. Run 'bow env create <name>'.")
        return

    click.echo(f"{'':2s} {'NAME':20s} {'PATH'}")
    click.echo(f"{'':2s} {'─' * 20} {'─' * 40}")
    for env in envs:
        marker = "* " if env.name == active else "  "
        click.echo(f"{marker}{env.name:20s} {env.path}")


@env_cmd.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def env_delete(name, yes):
    """Delete an environment."""
    from bow.oci.env import delete_env, EnvError

    if not yes:
        if not click.confirm(f"Delete environment '{name}'?"):
            return

    try:
        delete_env(name)
        click.echo(f"✓ Environment '{name}' deleted.")
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
