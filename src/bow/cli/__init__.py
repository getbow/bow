"""
bow.cli — CLI entry point.

Commands:
  bow template [chart] [flags]   — YAML render (without applying)
  bow up [chart] [flags]         — Deploy
  bow list                       — List installed charts
  bow inspect <chart>            — Chart details
  bow lock [flags]               — Create/update lock file
  bow status                     — Show workspace status
"""

import click

from bow.cli.template import template_cmd
from bow.cli.up import up_cmd
from bow.cli.list_cmd import list_cmd
from bow.cli.inspect_cmd import inspect_cmd
from bow.cli.lock_cmd import lock_cmd
from bow.cli.status_cmd import status_cmd


@click.group()
@click.version_option(package_name="bow")
def main():
    """bow — Pythonic Kubernetes DSL."""
    pass


main.add_command(template_cmd, "template")
main.add_command(up_cmd, "up")
main.add_command(list_cmd, "list")
main.add_command(inspect_cmd, "inspect")
main.add_command(lock_cmd, "lock")
main.add_command(status_cmd, "status")
