"""
tests/test_charts.py — Chart tests.

Redis, Redmine charts and component composition.
"""

import os
import sys
import yaml
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bow.core.stack import _reset
from bow.chart.registry import register_chart, get_chart, reset_registry
from bow_postgresql import PostgreSQLChart, pg_container, pg_service
from bow_redis import RedisChart, redis_container
from bow_redmine import RedmineChart, redmine_container, redmine_ingress
from bow.core.manifest import manifest
from bow.core.resources import (
    Deployment, Container, Service, Ingress,
    Port, EnvVar, IngressRule,
)


@pytest.fixture(autouse=True)
def clean():
    _reset()
    reset_registry()
    register_chart(PostgreSQLChart)
    register_chart(RedisChart)
    register_chart(RedmineChart)
    yield
    _reset()
    reset_registry()


# ─────────────────────────────────────────────
# REDIS CHART
# ─────────────────────────────────────────────
class TestRedisChart:
    def test_default_render(self):
        chart = get_chart("redis")
        m = chart.template()
        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        assert "Deployment" in kinds
        assert "PersistentVolumeClaim" in kinds
        assert "Service" in kinds

    def test_redis_container(self):
        chart = get_chart("redis")
        m = chart.template()
        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        assert c["image"] == "redis:7"
        assert any(p["containerPort"] == 6379 for p in c["ports"])
        assert "livenessProbe" in c
        assert "readinessProbe" in c

    def test_redis_custom_version(self):
        chart = get_chart("redis")
        m = chart.template(set_args=["version=6"])
        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        assert c["image"] == "redis:6"

    def test_redis_with_password(self):
        chart = get_chart("redis")
        m = chart.template(set_args=["password_secret=redis-pass"])
        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in c.get("env", [])]
        assert "REDIS_PASSWORD" in env_names

    def test_redis_no_persistence(self):
        chart = get_chart("redis")
        m = chart.template(set_args=["persistence.enabled=false"])
        kinds = [d["kind"] for d in m.to_dicts()]
        assert "PersistentVolumeClaim" not in kinds


# ─────────────────────────────────────────────
# REDMINE CHART
# ─────────────────────────────────────────────
class TestRedmineChart:
    def test_default_render(self):
        chart = get_chart("redmine")
        m = chart.template()
        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        # PostgreSQL dependency + Redmine
        assert kinds.count("Deployment") == 2  # pg + redmine
        assert "Service" in kinds

    def test_redmine_container_env(self):
        chart = get_chart("redmine")
        m = chart.template()
        deps = [d for d in m.to_dicts() if d["kind"] == "Deployment"]
        # Redmine deployment (the second one)
        redmine_dep = [d for d in deps
                       if d["metadata"]["name"] == "redmine"][0]
        c = redmine_dep["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in c["env"]]
        assert "REDMINE_DB_POSTGRES" in env_names
        assert "REDMINE_DB_DATABASE" in env_names

    def test_redmine_disable_postgresql(self):
        chart = get_chart("redmine")
        m = chart.template(set_args=["postgresql.enabled=false"])
        deps = [d for d in m.to_dicts() if d["kind"] == "Deployment"]
        # Only redmine, postgresql dependency skipped
        assert len(deps) == 1
        assert deps[0]["metadata"]["name"] == "redmine"

    def test_redmine_with_ingress(self):
        chart = get_chart("redmine")
        m = chart.template(set_args=[
            "ingress.enabled=true",
            "ingress.host=redmine.example.com",
            "ingress.tls=true",
        ])
        docs = m.to_dicts()
        ingresses = [d for d in docs if d["kind"] == "Ingress"]
        assert len(ingresses) == 1
        ing = ingresses[0]
        assert ing["spec"]["tls"][0]["hosts"] == ["redmine.example.com"]

    def test_redmine_without_ingress(self):
        chart = get_chart("redmine")
        m = chart.template()
        kinds = [d["kind"] for d in m.to_dicts()]
        assert "Ingress" not in kinds

    def test_redmine_yaml_valid(self):
        chart = get_chart("redmine")
        m = chart.template()
        yaml_str = m.to_yaml()
        docs = list(yaml.safe_load_all(yaml_str))
        assert len(docs) >= 4  # pg pvc + pg dep + pg svc + redmine pvc + redmine dep + redmine svc


# ─────────────────────────────────────────────
# COMPONENT COMPOSITION — external usage
# ─────────────────────────────────────────────
class TestComponentComposition:
    def test_pg_container_standalone(self):
        """pg_container can be used directly."""
        with manifest() as m:
            with Deployment("custom-db"):
                with pg_container(database="custom_db", image="postgres:15"):
                    EnvVar("EXTRA_CONFIG", "value")  # Extend
                Service(port=5432)

        dep = m.to_dicts()[0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in c["env"]]
        assert "POSTGRES_DB" in env_names
        assert "EXTRA_CONFIG" in env_names  # extended with `with`

    def test_redis_container_standalone(self):
        """redis_container can be used directly."""
        with manifest() as m:
            with Deployment("cache"):
                with redis_container(name="cache", image="redis:6"):
                    EnvVar("CUSTOM", "yes")
                Service(port=6379)

        dep = m.to_dicts()[0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        assert c["image"] == "redis:6"
        env_names = [e["name"] for e in c.get("env", [])]
        assert "CUSTOM" in env_names

    def test_redmine_container_extend(self):
        """redmine_container can be extended."""
        with manifest() as m:
            with Deployment("my-redmine"):
                with redmine_container(db_host="external-pg"):
                    EnvVar("REDMINE_PLUGINS_MIGRATE", "true")
                Service(port=3000)

        dep = m.to_dicts()[0]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in c["env"]]
        assert "REDMINE_DB_POSTGRES" in env_names
        assert "REDMINE_PLUGINS_MIGRATE" in env_names

    def test_mixed_components(self):
        """Different chart components used together."""
        with manifest() as m:
            with Deployment("pg"):
                with pg_container(database="app"):
                    pass
                Service(port=5432)

            with Deployment("cache"):
                with redis_container():
                    pass
                Service(port=6379)

            with Deployment("app"):
                with Container("app", image="myorg/app:v1"):
                    Port(8080)
                    EnvVar("DB_HOST", "pg")
                    EnvVar("REDIS_HOST", "cache")
                Service(port=8080)

        docs = m.to_dicts()
        deps = [d for d in docs if d["kind"] == "Deployment"]
        assert len(deps) == 3

    def test_pg_service_multiport(self):
        """pg_service component in multi-port mode."""
        with manifest() as m:
            with Deployment("pg"):
                with pg_container():
                    pass
                with pg_service(metrics=True):
                    pass

        docs = m.to_dicts()
        svc = [d for d in docs if d["kind"] == "Service"][0]
        assert len(svc["spec"]["ports"]) == 2
        port_names = [p.get("name") for p in svc["spec"]["ports"]]
        assert "pg" in port_names
        assert "metrics" in port_names

    def test_ingress_component_extend(self):
        """redmine_ingress can be extended."""
        with manifest() as m:
            with redmine_ingress(host="app.example.com", tls=True):
                IngressRule("/api", "api-service", 8080)

        ing = m.to_dicts()[0]
        paths = ing["spec"]["rules"][0]["http"]["paths"]
        assert len(paths) == 2  # / + /api
