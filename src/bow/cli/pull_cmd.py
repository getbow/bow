"""
bow.cli.pull_cmd — bow pull command.

  bow pull postgresql:16.4.0
  bow pull oci://ghcr.io/charts/postgresql:16.4.0
"""

import sys
import click


@click.command("pull")
@click.argument("reference")
def pull_cmd(reference):
    """Pull a chart from OCI registry and install into the active env."""
    from bow.oci.config import load_config
    from bow.oci.client import pull_chart, unpack_chart, OCIError
    from bow.oci.env import get_env, pip_install_in_env, EnvError

    cfg = load_config()

    # Parse reference: name:version or oci://reg/name:version
    name, version, registry_url = _parse_reference(reference, cfg)

    # Pull
    try:
        env = get_env()
        click.echo(f"Pulling {name}:{version} from {registry_url}...", err=True)
        click.echo(f"Environment: {env.name}", err=True)

        artifact = pull_chart(name, version, registry_url, env.cache_path)
        click.echo(f"Digest: {artifact.digest}", err=True)

        # Unpack + pip install
        if artifact.tar_path:
            import tempfile
            extract_dir = tempfile.mkdtemp()
            unpack_chart(artifact.tar_path, extract_dir)

            # pip install
            result = pip_install_in_env(extract_dir, env)
            if result.returncode != 0:
                click.echo(f"pip install failed:\n{result.stderr}", err=True)
                sys.exit(1)

            click.echo(f"✓ {name}:{version} installed in env '{env.name}'", err=True)
        else:
            click.echo("Error: No artifact to install.", err=True)
            sys.exit(1)

    except OCIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except EnvError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _parse_reference(ref: str, cfg) -> tuple[str, str, str]:
    """Parse reference: 'name:version' or 'oci://reg/name:version'.

    Returns:
        (name, version, registry_url)
    """
    if ref.startswith("oci://"):
        # oci://registry.example.com/charts/postgresql:16.4.0
        without_scheme = ref[6:]
        # Last segment is name:version
        parts = without_scheme.rsplit("/", 1)
        if len(parts) != 2:
            raise click.BadParameter(f"Invalid OCI reference: {ref}")
        registry_base = "oci://" + parts[0]
        name_version = parts[1]
    else:
        # postgresql:16.4.0 — use default registry
        name_version = ref
        registry_base = cfg.default_registry().url

    if ":" in name_version:
        name, version = name_version.rsplit(":", 1)
    else:
        raise click.BadParameter(
            f"Version required: {ref} → {ref}:<version>"
        )

    return name, version, registry_base
