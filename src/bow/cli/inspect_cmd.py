"""bow.cli.inspect_cmd — bow inspect command."""

import sys
import click
import yaml

from bow.chart.registry import get_chart, list_charts


@click.command("inspect")
@click.argument("chart_name")
def inspect_cmd(chart_name):
    """Show chart details."""
    chart = get_chart(chart_name)
    if chart is None:
        click.echo(f"Error: Chart '{chart_name}' not found.", err=True)
        available = list(list_charts().keys())
        if available:
            click.echo(f"Available: {', '.join(available)}", err=True)
        sys.exit(1)

    info = chart.info()

    click.echo(f"Name:        {info['name']}")
    click.echo(f"Version:     {info['version']}")
    if info["description"]:
        click.echo(f"Description: {info['description']}")

    # Dependencies
    if info["dependencies"]:
        click.echo(f"\nDependencies:")
        for dep in info["dependencies"]:
            cond = f" (condition: {dep['condition']})" if dep["condition"] else ""
            deploy = "deploy" if dep["deploy"] else "no-deploy"
            click.echo(f"  📦 {dep['chart']} [{deploy}]{cond}")

    # Default values
    if info["defaults"]:
        click.echo(f"\nDefault Values:")
        click.echo(yaml.dump(info["defaults"], default_flow_style=False, sort_keys=False))
