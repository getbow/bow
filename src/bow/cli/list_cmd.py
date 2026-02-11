"""bow.cli.list_cmd — bow list command."""

import click

from bow.chart.registry import list_charts


@click.command("list")
def list_cmd():
    """List installed charts."""
    charts = list_charts()

    if not charts:
        click.echo("No charts installed.")
        click.echo("Install a chart: pip install bow-<chart-name>")
        return

    click.echo(f"{'NAME':<20} {'VERSION':<12} {'DESCRIPTION'}")
    click.echo("─" * 60)
    for name, cls in sorted(charts.items()):
        version = getattr(cls, "version", "?")
        desc = getattr(cls, "description", "")
        click.echo(f"{name:<20} {version:<12} {desc}")
