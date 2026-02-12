"""
bow.cli.push_cmd — bow push command.

  bow push . --tag 16.4.0
  bow push ./charts/bow-postgresql
  bow push . --registry oci://ghcr.io/getbow/charts
"""

import sys
import click


@click.command("push")
@click.argument("chart_dir", default=".")
@click.option("--tag", "-t", default=None, help="Version tag override")
@click.option("--registry", "-r", default=None, help="Registry URL override")
def push_cmd(chart_dir, tag, registry):
    """Push a chart to an OCI registry."""
    from bow.oci.config import load_config
    from bow.oci.client import pack_chart, push_chart, OCIError

    cfg = load_config()

    # Resolve registry (always has a default now)
    if registry is None:
        registry = cfg.default_registry().url

    # Package
    try:
        click.echo(f"Packing chart from {chart_dir}...", err=True)
        artifact = pack_chart(chart_dir)

        if tag:
            artifact.version = tag

        click.echo(
            f"  {artifact.name}:{artifact.version} "
            f"({artifact.digest[:30]}...)",
            err=True,
        )

        # Push
        click.echo(f"Pushing to {registry}...", err=True)
        ref = push_chart(artifact, registry)
        click.echo(f"✓ Pushed to {ref}", err=True)

    except OCIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
