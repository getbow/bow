"""
bow.charts.redmine — Redmine chart.

Redmine chart with PostgreSQL dependency.
Component composition example: Redmine defines its own
container and uses PostgreSQL as a dependency.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from bow.chart.base import Chart
from bow.chart.dependency import ChartDep
from bow.core.resources import (
    Deployment, Container, Service,
    PersistentVolumeClaim, Ingress, IngressRule,
    Port, EnvVar, Resources, VolumeMount, Probe,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REUSABLE COMPONENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@contextmanager
def redmine_container(
    name: str = "redmine",
    image: str = "redmine:5.1",
    port: int = 3000,
    db_host: str = "redmine-db",
    db_port: int = 5432,
    db_name: str = "redmine",
    db_credentials_secret: str = "redmine-db-credentials",
    resources: dict | None = None,
):
    """Redmine main container component.

    Extra env, plugin mount etc. can be added inside the with block::

        with redmine_container(db_host="external-db"):
            EnvVar("REDMINE_PLUGINS_MIGRATE", "true")
            VolumeMount("/usr/src/redmine/plugins", "plugins")
    """
    with Container(name, image=image) as c:
        Port(port, name="http")

        # Database connection
        EnvVar("REDMINE_DB_POSTGRES", db_host)
        EnvVar("REDMINE_DB_PORT", str(db_port))
        EnvVar("REDMINE_DB_DATABASE", db_name)
        EnvVar("REDMINE_DB_USERNAME", secret_ref=db_credentials_secret,
               secret_key="POSTGRES_USER")
        EnvVar("REDMINE_DB_PASSWORD", secret_ref=db_credentials_secret,
               secret_key="POSTGRES_PASSWORD")

        # Resources
        res = resources or {}
        if res:
            Resources(
                cpu=res.get("cpu"),
                memory=res.get("memory"),
                limits_cpu=res.get("limits_cpu"),
                limits_memory=res.get("limits_memory"),
            )

        # Files volume
        VolumeMount("/usr/src/redmine/files", "redmine-files")

        # Probes
        Probe("liveness",
              http_get={"path": "/", "port": port},
              initial_delay=60, period=30, timeout=5)
        Probe("readiness",
              http_get={"path": "/", "port": port},
              initial_delay=30, period=10)

        yield c


@contextmanager
def redmine_ingress(
    name: str = "redmine",
    host: str | None = None,
    tls: bool = False,
    ingress_class: str = "nginx",
    service_name: str = "redmine",
    service_port: int = 3000,
):
    """Redmine Ingress component.

    Extra IngressRule can be added inside the with block::

        with redmine_ingress(host="redmine.example.com", tls=True):
            IngressRule("/api", "redmine-api", 8080)
    """
    with Ingress(name, host=host, tls=tls, ingress_class=ingress_class) as ing:
        IngressRule("/", service_name, service_port)
        yield ing


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHART CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class RedmineChart(Chart):
    name = "redmine"
    version = "5.1.0"
    description = "Redmine project management tool"

    requires = [
        ChartDep(
            chart="postgresql",
            deploy=True,
            condition="postgresql.enabled",
            default_values={
                "name": "redmine-db",
                "database": "redmine",
                "credentials_secret": "redmine-db-credentials",
                "storage": "20Gi",
            },
        ),
    ]

    def render(self, values: dict[str, Any]) -> None:
        v = values
        redmine_name = v.get("name", "redmine")
        port = v.get("service", {}).get("port", 3000)
        pg = v.get("postgresql", {})

        with Deployment(redmine_name, replicas=v.get("replicas", 1)):
            # Main container — extendable with `with`
            with redmine_container(
                name=redmine_name,
                image=f"redmine:{v.get('version', '5.1')}",
                port=port,
                db_host=pg.get("name", "redmine-db"),
                db_port=5432,
                db_name=pg.get("database", "redmine"),
                db_credentials_secret=pg.get("credentials_secret",
                                              "redmine-db-credentials"),
                resources=v.get("resources"),
            ):
                pass  # Default config

            # Files PVC
            PersistentVolumeClaim(
                "redmine-files",
                size=v.get("storage", "30Gi"),
                storage_class=v.get("storage_class"),
            )

            # Service
            Service(
                port=port,
                type=v.get("service", {}).get("type", "ClusterIP"),
            )

        # Ingress (optional, parametric)
        ing = v.get("ingress", {})
        if ing.get("enabled", False) and ing.get("host"):
            with redmine_ingress(
                name=f"{redmine_name}-ingress",
                host=ing["host"],
                tls=ing.get("tls", False),
                ingress_class=ing.get("ingress_class", "nginx"),
                service_name=redmine_name,
                service_port=port,
            ):
                pass
