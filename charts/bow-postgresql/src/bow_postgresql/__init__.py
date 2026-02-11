"""
bow.charts.postgresql — PostgreSQL chart.

Written with reusable components (@contextmanager).
Components can be used both within the chart and
externally via composition.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from bow.chart.base import Chart
from bow.core.resources import (
    Deployment, StatefulSet, Container, Service, ServicePort,
    PersistentVolumeClaim,
    Port, EnvVar, Resources, VolumeMount, Probe,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REUSABLE COMPONENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@contextmanager
def pg_container(
    name: str = "postgresql",
    image: str = "postgres:16",
    port: int = 5432,
    database: str = "appdb",
    credentials_secret: str = "pg-credentials",
    resources: dict | None = None,
    probes: dict | None = None,
):
    """PostgreSQL main container component.

    Extra EnvVar, VolumeMount etc. can be added inside the with block::

        with pg_container(database="mydb"):
            EnvVar("POSTGRES_EXTRA_CONF", "some_value")
    """
    with Container(name, image=image) as c:
        Port(port, name="pg")

        # Core env
        EnvVar("POSTGRES_DB", database)
        EnvVar("PGDATA", "/var/lib/postgresql/data/pgdata")
        EnvVar("POSTGRES_USER", secret_ref=credentials_secret,
               secret_key="POSTGRES_USER")
        EnvVar("POSTGRES_PASSWORD", secret_ref=credentials_secret,
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

        # Data volume
        VolumeMount("/var/lib/postgresql/data", "pgdata")

        # Probes
        _probes = probes or {}
        liveness = _probes.get("liveness", {})
        if liveness.get("enabled", True):
            Probe("liveness",
                  tcp_socket={"port": port},
                  initial_delay=liveness.get("initial_delay", 30),
                  period=liveness.get("period", 10))

        readiness = _probes.get("readiness", {})
        if readiness.get("enabled", True):
            Probe("readiness",
                  exec_command=["pg_isready", "-U", "postgres"],
                  initial_delay=readiness.get("initial_delay", 5),
                  period=readiness.get("period", 5))

        yield c


@contextmanager
def pg_metrics_sidecar(
    database: str = "appdb",
    credentials_secret: str = "pg-credentials",
    image: str = "prometheuscommunity/postgres-exporter:latest",
):
    """Prometheus metrics exporter sidecar component."""
    with Container("exporter", image=image) as c:
        Port(9187, name="metrics")
        EnvVar("DATA_SOURCE_URI",
               f"localhost:5432/{database}?sslmode=disable")
        EnvVar("DATA_SOURCE_USER", secret_ref=credentials_secret,
               secret_key="POSTGRES_USER")
        EnvVar("DATA_SOURCE_PASS", secret_ref=credentials_secret,
               secret_key="POSTGRES_PASSWORD")
        yield c


@contextmanager
def pg_service(port: int = 5432, type: str = "ClusterIP", metrics: bool = False):
    """PostgreSQL service component.

    If metrics enabled, port 9187 is also added::

        with pg_service(metrics=True):
            pass
    """
    if metrics:
        with Service(type=type) as svc:
            ServicePort(port, name="pg")
            ServicePort(9187, name="metrics")
            yield svc
    else:
        svc = Service(port=port, type=type)
        yield svc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHART CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PostgreSQLChart(Chart):
    name = "postgresql"
    version = "16.4.0"
    description = "PostgreSQL relational database"

    def render(self, values: dict[str, Any]) -> None:
        v = values
        pg_name = v.get("name", "postgresql")
        creds = v.get("credentials_secret", "pg-credentials")
        database = v.get("database", "appdb")
        port = v.get("service", {}).get("port", 5432)
        metrics_enabled = v.get("metrics", {}).get("enabled", False)

        with Deployment(pg_name, replicas=v.get("replicas", 1)):
            # Main container — with block, extendable
            with pg_container(
                name=pg_name,
                image=f"postgres:{v.get('version', '16')}",
                port=port,
                database=database,
                credentials_secret=creds,
                resources=v.get("resources"),
                probes=v.get("probes"),
            ):
                pass  # Default config is sufficient

            # Metrics sidecar — conditional component
            if metrics_enabled:
                with pg_metrics_sidecar(
                    database=database,
                    credentials_secret=creds,
                    image=v.get("metrics", {}).get("image",
                        "prometheuscommunity/postgres-exporter:latest"),
                ):
                    pass

            # PVC
            PersistentVolumeClaim(
                "pgdata",
                size=v.get("storage", "10Gi"),
                storage_class=v.get("storage_class"),
            )

            # Service — multi-port if metrics enabled
            with pg_service(
                port=port,
                type=v.get("service", {}).get("type", "ClusterIP"),
                metrics=metrics_enabled,
            ):
                pass
