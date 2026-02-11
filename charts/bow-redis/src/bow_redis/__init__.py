"""
bow.charts.redis — Redis chart.

Redis chart written with reusable components.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from bow.chart.base import Chart
from bow.core.resources import (
    Deployment, Container, Service,
    PersistentVolumeClaim,
    Port, EnvVar, Resources, VolumeMount, Probe,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REUSABLE COMPONENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@contextmanager
def redis_container(
    name: str = "redis",
    image: str = "redis:7",
    port: int = 6379,
    password_secret: str | None = None,
    resources: dict | None = None,
    config: dict | None = None,
):
    """Redis container component.

    Extra configuration can be added inside the with block::

        with redis_container(password_secret="redis-pass"):
            EnvVar("REDIS_EXTRA", "value")
    """
    # Command: config parametreleri
    cmd = ["redis-server"]
    cfg = config or {}
    if cfg.get("maxmemory"):
        cmd.extend(["--maxmemory", cfg["maxmemory"]])
    if cfg.get("maxmemory_policy"):
        cmd.extend(["--maxmemory-policy", cfg["maxmemory_policy"]])
    if password_secret:
        cmd.extend(["--requirepass", "$(REDIS_PASSWORD)"])

    with Container(name, image=image, command=cmd) as c:
        Port(port, name="redis")

        if password_secret:
            EnvVar("REDIS_PASSWORD", secret_ref=password_secret,
                   secret_key="REDIS_PASSWORD")

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
        VolumeMount("/data", "redis-data")

        # Probes
        Probe("liveness",
              exec_command=["redis-cli", "ping"],
              initial_delay=10, period=10)
        Probe("readiness",
              exec_command=["redis-cli", "ping"],
              initial_delay=5, period=5)

        yield c


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHART CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class RedisChart(Chart):
    name = "redis"
    version = "7.2.0"
    description = "Redis in-memory data store"

    def render(self, values: dict[str, Any]) -> None:
        v = values
        redis_name = v.get("name", "redis")
        port = v.get("service", {}).get("port", 6379)

        with Deployment(redis_name, replicas=v.get("replicas", 1)):
            with redis_container(
                name=redis_name,
                image=f"redis:{v.get('version', '7')}",
                port=port,
                password_secret=v.get("password_secret"),
                resources=v.get("resources"),
                config=v.get("config"),
            ):
                pass  # Default config

            # PVC
            if v.get("persistence", {}).get("enabled", True):
                PersistentVolumeClaim(
                    "redis-data",
                    size=v.get("storage", "5Gi"),
                    storage_class=v.get("storage_class"),
                )

            # Service
            Service(
                port=port,
                type=v.get("service", {}).get("type", "ClusterIP"),
            )
