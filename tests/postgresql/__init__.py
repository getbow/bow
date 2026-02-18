"""
bow.charts.postgresql — PostgreSQL chart.

Minimal PostgreSQL deployment for Kubernetes using bow DSL.
"""

from __future__ import annotations
from contextlib import contextmanager
from typing import Any

from bow import Deployment
from bow.chart.base import Chart
from bow.core.resources import (
    StatefulSet, Container, Secret, Service, PersistentVolumeClaim,
    Port, EnvVar, Resources, Probe
)
from bow.utils import full_image, apply_resources


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REUSABLE COMPONENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@contextmanager
def postgresql_container(
    name: str, 
    image: str, 
    port: int = 5432, 
    secret_name: str = "postgres",
    postgres_user: str = "postgres",
    postgres_db: str = "postgres",
    resources: dict | None = None) -> None:
    """PostgreSQL main container component."""
    with Container(name, image=image):
        Port(port, name="postgresql")

        # Core postgres settings
        EnvVar("POSTGRES_USER", postgres_user)
        EnvVar("POSTGRES_DB", postgres_db)
        EnvVar("POSTGRES_PASSWORD", secret_ref=secret_name, secret_key="POSTGRES_PASSWORD")
        EnvVar("PGDATA", "/var/lib/postgresql/data")
        
        apply_resources(resources)
        yield

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHART CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PostgreSQLChart(Chart):
    name = "postgresql"
    description = "PostgreSQL chart for bow."

    def render(self, values: dict[str, Any]) -> None:
        name = values.get("name", self.name)
        image = full_image(values.get("image", {}))
        port = values.get("service", {}).get("port", 5432)
        resources = values.get("resources")        
        architecture = values.get("architecture", "standalone")
        persistence = values.get("persistence", {})

        if architecture == "replication":
            with StatefulSet(name, replicas=values.get("replicas", 1), service_name=f"{name}-headless"):
                with postgresql_container(name, image, port, resources=resources):
                    pass

                if persistence.get("enabled", True):
                    PersistentVolumeClaim("data", size=persistence.get("size", "8Gi"))

                Service(port=port, type=values.get("service", {}).get("type", "ClusterIP"))
        else:
            with Deployment(name, replicas=values.get("replicas", 1)):
                with postgresql_container(name, image, port, resources=resources):
                    pass

                if persistence.get("enabled", True):
                    PersistentVolumeClaim("data", size=persistence.get("size", "8Gi"))

                Service(port=port, type=values.get("service", {}).get("type", "ClusterIP"))
