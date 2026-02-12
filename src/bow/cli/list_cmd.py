"""bow.cli.list_cmd — bow list command."""

import json
import subprocess
from pathlib import Path
from typing import Any

import click
import yaml

from bow.chart.registry import list_charts, get_chart_class


def _get_deployed_info() -> dict[str, dict[str, Any]]:
    """Get deployed chart info from Kubernetes cluster.

    Returns:
        Dict keyed by chart name → {namespace, app_version, updated, revision}
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "all", "-A",
             "-l", "bow.io/managed-by=bow", "-o", "json"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        items = data.get("items", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return {}

    deployed: dict[str, dict[str, Any]] = {}
    for item in items:
        labels = item.get("metadata", {}).get("labels", {})
        chart_name = labels.get("bow.io/chart")
        if not chart_name:
            continue

        namespace = item.get("metadata", {}).get("namespace", "default")
        created = item.get("metadata", {}).get("creationTimestamp", "")

        key = f"{chart_name}-{namespace}"
        if key not in deployed:
            deployed[key] = {
                "name": chart_name,
                "namespace": namespace,
                "app_version": None,
                "updated": created,
                "revision": 1,
            }

        # Extract app version from container image tag
        containers = (
            item.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        for c in containers:
            image = c.get("image", "")
            if ":" in image:
                deployed[key]["app_version"] = image.rsplit(":", 1)[-1]
                break

    return deployed


def _get_app_version_from_defaults(chart_name: str) -> str:
    """Get app version from a chart's defaults.yaml (image.tag)."""
    try:
        cls = get_chart_class(chart_name)
        if not cls:
            return "?"
        instance = cls()
        defaults = instance.default_values()
        return str(defaults.get("image", {}).get("tag", "?"))
    except Exception:
        return "?"


@click.command("list")
def list_cmd():
    """List charts — shows both available and deployed."""

    available = list_charts()          # {name: cls}
    deployed = _get_deployed_info()    # {key: info}

    if not available and not deployed:
        click.echo("No charts found.")
        click.echo("Install a chart: pip install bow-<chart-name>")
        return

    # Index deployed by chart name for quick lookup
    deployed_by_name: dict[str, list[dict]] = {}
    for info in deployed.values():
        deployed_by_name.setdefault(info["name"], []).append(info)

    # Header — Helm-like
    click.echo(
        f"{'NAME':<15} {'NAMESPACE':<15} {'REVISION':<10} "
        f"{'UPDATED':<32} {'STATUS':<12} {'CHART':<25} {'APP VERSION'}"
    )
    click.echo("─" * 130)

    printed: set[str] = set()

    # 1) Deployed charts first
    for entries in deployed_by_name.values():
        for info in entries:
            name = info["name"]
            namespace = info["namespace"]
            revision = info["revision"]
            updated = info["updated"]
            app_version = info["app_version"] or "?"

            # Chart version from package metadata (pyproject.toml)
            cls = available.get(name)
            chart_version = getattr(cls, "version", "?") if cls else "?"
            chart_label = f"{name}-{chart_version}"

            click.echo(
                f"{name:<15} {namespace:<15} {revision:<10} "
                f"{updated:<32} {'deployed':<12} {chart_label:<25} {app_version}"
            )
            printed.add(name)

    # 2) Available but not deployed
    for name, cls in sorted(available.items()):
        if name in printed:
            continue

        chart_version = getattr(cls, "version", "?")
        chart_label = f"{name}-{chart_version}"
        app_version = _get_app_version_from_defaults(name)

        click.echo(
            f"{name:<15} {'':<15} {'':<10} "
            f"{'':<32} {'':<12} {chart_label:<25} {app_version}"
        )

