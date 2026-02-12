"""
bow.cli.registry_cmd — bow registry command.

  bow registry add default oci://ghcr.io/getbow/charts
  bow registry add harbor oci://harbor.internal/bow --default
  bow registry list
  bow registry remove harbor
  bow registry login ghcr.io
  bow registry login ghcr.io -u USERNAME -p TOKEN
"""

import sys
import click


@click.group("registry")
def registry_cmd():
    """OCI registry management."""
    pass


@registry_cmd.command("login")
@click.argument("hostname")
@click.option("--username", "-u", default=None, help="Registry username")
@click.option("--password", "-p", default=None,
              help="Registry password/token (or use --password-stdin)")
@click.option("--password-stdin", is_flag=True,
              help="Read password from stdin")
def registry_login(hostname, username, password, password_stdin):
    """Login to an OCI registry.

    \b
    Examples:
      bow registry login ghcr.io
      bow registry login ghcr.io -u USERNAME -p ghp_TOKEN
      echo $GITHUB_TOKEN | bow registry login ghcr.io -u USERNAME --password-stdin
    """
    import oras.client

    if password_stdin:
        password = sys.stdin.readline().strip()

    if not username:
        username = click.prompt("Username")
    if not password:
        password = click.prompt("Password/Token", hide_input=True)

    try:
        client = oras.client.OrasClient()
        client.login(
            hostname=hostname,
            username=username,
            password=password,
        )
        click.echo(f"✓ Logged in to {hostname}")
    except Exception as e:
        click.echo(f"Error: Login failed: {e}", err=True)
        sys.exit(1)


@registry_cmd.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--default", "is_default", is_flag=True,
              help="Set as default registry")
def registry_add(name, url, is_default):
    """Add a registry."""
    from bow.oci.config import load_config, save_config, RegistryConfig

    cfg = load_config()

    # If setting as default, clear default flag from others
    if is_default:
        for reg in cfg.registries.values():
            reg.default = False

    cfg.registries[name] = RegistryConfig(
        name=name, url=url, default=is_default,
    )

    # Auto-add to whitelist
    if url not in cfg.allowed_registries:
        cfg.allowed_registries.append(url)

    save_config(cfg)
    default_mark = " (default)" if is_default else ""
    click.echo(f"✓ Registry '{name}' added: {url}{default_mark}")


@registry_cmd.command("list")
def registry_list():
    """List configured registries."""
    from bow.oci.config import load_config

    cfg = load_config()

    if not cfg.registries:
        click.echo("No registries configured.")
        click.echo("Run: bow registry add <name> <url>")
        return

    click.echo(f"{'':2s} {'NAME':20s} {'URL'}")
    click.echo(f"{'':2s} {'─' * 20} {'─' * 40}")
    for name, reg in cfg.registries.items():
        marker = "* " if reg.default else "  "
        click.echo(f"{marker}{name:20s} {reg.url}")

    if cfg.allowed_registries:
        click.echo(f"\nAllowed registries:")
        for url in cfg.allowed_registries:
            click.echo(f"  ✓ {url}")


@registry_cmd.command("remove")
@click.argument("name")
def registry_remove(name):
    """Remove a registry."""
    from bow.oci.config import load_config, save_config

    cfg = load_config()
    if name not in cfg.registries:
        click.echo(f"Registry '{name}' not found.", err=True)
        sys.exit(1)

    # Also remove from whitelist
    url = cfg.registries[name].url
    if url in cfg.allowed_registries:
        cfg.allowed_registries.remove(url)

    del cfg.registries[name]
    save_config(cfg)
    click.echo(f"✓ Registry '{name}' removed.")
