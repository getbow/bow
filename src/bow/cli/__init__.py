"""
bow.cli — CLI entry point.

Commands:
  bow template [chart] [flags]   — YAML render (without applying)
  bow up [chart] [flags]         — Deploy
  bow list                       — List installed charts
  bow inspect <chart>            — Chart details
  bow lock [flags]               — Create/update lock file
  bow status                     — Show workspace status
  bow env create/use/list/delete — Environment management
  bow pull <chart:version>       — Pull chart from OCI
  bow push [dir]                 — Push chart to OCI
  bow registry add/list/remove   — Registry management  
"""

import click

from bow.cli.template import template_cmd
from bow.cli.up import up_cmd
from bow.cli.list_cmd import list_cmd
from bow.cli.inspect_cmd import inspect_cmd
from bow.cli.lock_cmd import lock_cmd
from bow.cli.status_cmd import status_cmd
from bow.cli.env_cmd import env_cmd
from bow.cli.pull_cmd import pull_cmd
from bow.cli.push_cmd import push_cmd
from bow.cli.registry_cmd import registry_cmd
from bow.cli.install_cmd import install_cmd
from bow.cli.uninstall_cmd import uninstall_cmd


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
main.add_command(env_cmd, "env")
main.add_command(pull_cmd, "pull")
main.add_command(push_cmd, "push")
main.add_command(registry_cmd, "registry")
main.add_command(install_cmd, "install")
main.add_command(uninstall_cmd, "uninstall")