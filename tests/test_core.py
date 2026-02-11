"""
tests/test_core.py — Phase 1 tests.

Tests all resources and context manager behaviors
of the core module.
"""

import yaml
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bow.core.stack import _reset
from bow.core.manifest import manifest
from bow.core.resources import (
    Namespace, Deployment, StatefulSet, CronJob,
    Container, Service, ServicePort, ConfigMap, Secret,
    Ingress, PersistentVolumeClaim,
    Port, EnvVar, Resources, VolumeMount, Probe,
    Data, IngressRule,
    EmptyDirVolume, ConfigMapVolume, SecretVolume,
)


@pytest.fixture(autouse=True)
def clean_stack():
    """Clean the stack before each test."""
    _reset()
    yield
    _reset()


# ─────────────────────────────────────────────
# BASIC DEPLOYMENT
# ─────────────────────────────────────────────
class TestDeployment:
    def test_simple_deployment(self):
        with manifest() as m:
            with Deployment("nginx"):
                with Container("nginx", image="nginx:latest"):
                    Port(80)

        docs = m.to_dicts()
        assert len(docs) == 1
        dep = docs[0]
        assert dep["kind"] == "Deployment"
        assert dep["metadata"]["name"] == "nginx"
        assert dep["spec"]["replicas"] == 1
        containers = dep["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 1
        assert containers[0]["name"] == "nginx"
        assert containers[0]["image"] == "nginx:latest"
        assert containers[0]["ports"][0]["containerPort"] == 80

    def test_deployment_with_replicas(self):
        with manifest() as m:
            with Deployment("api", replicas=3):
                with Container("api", image="myorg/api:v1"):
                    pass

        dep = m.to_dicts()[0]
        assert dep["spec"]["replicas"] == 3

    def test_deployment_with_service(self):
        with manifest() as m:
            with Deployment("web"):
                with Container("web", image="nginx:latest"):
                    Port(80)
                Service(port=80)

        docs = m.to_dicts()
        assert len(docs) == 2  # Deployment + Service
        assert docs[0]["kind"] == "Deployment"
        assert docs[1]["kind"] == "Service"
        # Service selector comes from Deployment labels
        assert docs[1]["spec"]["selector"] == {"app": "web"}

    def test_deployment_with_pvc(self):
        with manifest() as m:
            with Deployment("db"):
                with Container("db", image="postgres:16"):
                    VolumeMount("/var/lib/postgresql/data", "pgdata")
                PersistentVolumeClaim("pgdata", size="50Gi")

        docs = m.to_dicts()
        assert len(docs) == 2  # PVC + Deployment
        assert docs[0]["kind"] == "PersistentVolumeClaim"
        assert docs[0]["spec"]["resources"]["requests"]["storage"] == "50Gi"
        # Deployment volumes
        dep = docs[1]
        assert len(dep["spec"]["template"]["spec"]["volumes"]) == 1
        assert dep["spec"]["template"]["spec"]["volumes"][0]["name"] == "pgdata"


# ─────────────────────────────────────────────
# CONTAINER DETAILS
# ─────────────────────────────────────────────
class TestContainer:
    def test_envvar_plain(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    EnvVar("DB_HOST", "localhost")
                    EnvVar("DB_PORT", "5432")

        containers = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"]
        env = containers[0]["env"]
        assert len(env) == 2
        assert env[0] == {"name": "DB_HOST", "value": "localhost"}
        assert env[1] == {"name": "DB_PORT", "value": "5432"}

    def test_envvar_secret_ref(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    EnvVar("PASSWORD", secret_ref="my-secret", secret_key="db-pass")

        env = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert env[0]["valueFrom"]["secretKeyRef"]["name"] == "my-secret"
        assert env[0]["valueFrom"]["secretKeyRef"]["key"] == "db-pass"

    def test_envvar_configmap_ref(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    EnvVar("CONFIG", configmap_ref="my-config", configmap_key="setting")

        env = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert env[0]["valueFrom"]["configMapKeyRef"]["name"] == "my-config"

    def test_resources(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    Resources(cpu="250m", memory="256Mi",
                              limits_cpu="500m", limits_memory="512Mi")

        res = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert res["requests"]["cpu"] == "250m"
        assert res["requests"]["memory"] == "256Mi"
        assert res["limits"]["cpu"] == "500m"
        assert res["limits"]["memory"] == "512Mi"

    def test_probes(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    Probe("liveness", http_get={"path": "/health", "port": 8080},
                          initial_delay=10, period=30)
                    Probe("readiness", tcp_socket={"port": 8080})

        c = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in c
        assert c["livenessProbe"]["httpGet"]["path"] == "/health"
        assert c["livenessProbe"]["initialDelaySeconds"] == 10
        assert "readinessProbe" in c
        assert c["readinessProbe"]["tcpSocket"]["port"] == 8080

    def test_volume_mount(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    VolumeMount("/config", "cfg", read_only=True)

        c = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"][0]
        assert c["volumeMounts"][0]["mountPath"] == "/config"
        assert c["volumeMounts"][0]["readOnly"] is True

    def test_port_outside_container_raises(self):
        with manifest() as m:
            with Deployment("app"):
                with pytest.raises(TypeError):
                    Port(80)

    def test_multiple_containers(self):
        with manifest() as m:
            with Deployment("app"):
                with Container("app", image="app:v1"):
                    Port(8080)
                with Container("sidecar", image="envoy:latest"):
                    Port(9090)

        containers = m.to_dicts()[0]["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 2
        assert containers[0]["name"] == "app"
        assert containers[1]["name"] == "sidecar"


# ─────────────────────────────────────────────
# SERVICE
# ─────────────────────────────────────────────
class TestService:
    def test_service_leaf_mode(self):
        with manifest() as m:
            with Deployment("web"):
                with Container("web", image="nginx"):
                    Port(80)
                Service(port=80)

        svc = m.to_dicts()[1]
        assert svc["spec"]["ports"][0]["port"] == 80
        assert svc["spec"]["selector"] == {"app": "web"}

    def test_service_with_mode(self):
        with manifest() as m:
            with Deployment("web"):
                with Container("web", image="nginx"):
                    Port(80)
                    Port(443)
                with Service(type="NodePort"):
                    ServicePort(80, name="http")
                    ServicePort(443, name="https", node_port=30443)

        svc = m.to_dicts()[1]
        assert svc["spec"]["type"] == "NodePort"
        assert len(svc["spec"]["ports"]) == 2
        assert svc["spec"]["ports"][1]["nodePort"] == 30443

    def test_standalone_service(self):
        """Service can be used outside Deployment."""
        with manifest() as m:
            with Service(name="external-db", type="ExternalName"):
                pass

        docs = m.to_dicts()
        assert len(docs) == 1
        assert docs[0]["kind"] == "Service"


# ─────────────────────────────────────────────
# CONFIGMAP & SECRET
# ─────────────────────────────────────────────
class TestConfigMapSecret:
    def test_configmap_with_data(self):
        with manifest() as m:
            with ConfigMap("app-config"):
                Data("database_url", "postgresql://localhost:5432/mydb")
                Data("redis_url", "redis://localhost:6379")

        cm = m.to_dicts()[0]
        assert cm["kind"] == "ConfigMap"
        assert cm["data"]["database_url"] == "postgresql://localhost:5432/mydb"
        assert cm["data"]["redis_url"] == "redis://localhost:6379"

    def test_configmap_leaf_mode(self):
        with manifest() as m:
            ConfigMap("app-config", data={"key": "value"})

        cm = m.to_dicts()[0]
        assert cm["data"]["key"] == "value"

    def test_secret(self):
        with manifest() as m:
            with Secret("db-creds"):
                Data("username", "admin")
                Data("password", "s3cret")

        sec = m.to_dicts()[0]
        assert sec["kind"] == "Secret"
        assert sec["type"] == "Opaque"
        # base64 encoded
        import base64
        decoded = base64.b64decode(sec["data"]["password"]).decode()
        assert decoded == "s3cret"

    def test_secret_string_data(self):
        with manifest() as m:
            Secret("my-secret", string_data={"token": "abc123"})

        sec = m.to_dicts()[0]
        assert sec["stringData"]["token"] == "abc123"


# ─────────────────────────────────────────────
# INGRESS
# ─────────────────────────────────────────────
class TestIngress:
    def test_simple_ingress(self):
        with manifest() as m:
            with Ingress("my-ingress", host="app.example.com", tls=True):
                IngressRule("/", "web", 80)
                IngressRule("/api", "api", 8080)

        ing = m.to_dicts()[0]
        assert ing["kind"] == "Ingress"
        assert ing["spec"]["ingressClassName"] == "nginx"
        assert ing["spec"]["tls"][0]["hosts"] == ["app.example.com"]
        # Same host → one rule, two paths
        assert len(ing["spec"]["rules"]) == 1
        assert len(ing["spec"]["rules"][0]["http"]["paths"]) == 2

    def test_multi_host_ingress(self):
        with manifest() as m:
            with Ingress("multi", host="app.example.com"):
                IngressRule("/", "web", 80)
                IngressRule("/", "api", 8080, host="api.example.com")

        ing = m.to_dicts()[0]
        assert len(ing["spec"]["rules"]) == 2


# ─────────────────────────────────────────────
# STATEFULSET
# ─────────────────────────────────────────────
class TestStatefulSet:
    def test_statefulset(self):
        with manifest() as m:
            with StatefulSet("pg", replicas=3):
                with Container("pg", image="postgres:16"):
                    Port(5432)
                    VolumeMount("/var/lib/postgresql/data", "pgdata")
                PersistentVolumeClaim("pgdata", size="100Gi")
                Service(port=5432)

        docs = m.to_dicts()
        ss = docs[0]
        assert ss["kind"] == "StatefulSet"
        assert ss["spec"]["replicas"] == 3
        assert ss["spec"]["serviceName"] == "pg"
        assert len(ss["spec"]["volumeClaimTemplates"]) == 1
        assert ss["spec"]["volumeClaimTemplates"][0]["spec"]["resources"]["requests"]["storage"] == "100Gi"
        # Service
        assert docs[1]["kind"] == "Service"

    def test_statefulset_service_name(self):
        with manifest() as m:
            with StatefulSet("redis", service_name="redis-headless"):
                with Container("redis", image="redis:7"):
                    Port(6379)

        ss = m.to_dicts()[0]
        assert ss["spec"]["serviceName"] == "redis-headless"


# ─────────────────────────────────────────────
# CRONJOB
# ─────────────────────────────────────────────
class TestCronJob:
    def test_cronjob(self):
        with manifest() as m:
            with CronJob("backup", schedule="0 2 * * *"):
                with Container("backup", image="myorg/backup:v1"):
                    EnvVar("DB_HOST", "postgresql")

        cj = m.to_dicts()[0]
        assert cj["kind"] == "CronJob"
        assert cj["spec"]["schedule"] == "0 2 * * *"
        containers = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
        assert containers[0]["image"] == "myorg/backup:v1"


# ─────────────────────────────────────────────
# VOLUMES
# ─────────────────────────────────────────────
class TestVolumes:
    def test_emptydir(self):
        with manifest() as m:
            with Deployment("app"):
                EmptyDirVolume("tmp", medium="Memory")
                with Container("app", image="app:v1"):
                    VolumeMount("/tmp", "tmp")

        dep = m.to_dicts()[0]
        vols = dep["spec"]["template"]["spec"]["volumes"]
        assert vols[0]["name"] == "tmp"
        assert vols[0]["emptyDir"]["medium"] == "Memory"

    def test_configmap_volume(self):
        with manifest() as m:
            with Deployment("app"):
                ConfigMapVolume("cfg", "app-config")
                with Container("app", image="app:v1"):
                    VolumeMount("/config", "cfg", read_only=True)

        dep = m.to_dicts()[0]
        vols = dep["spec"]["template"]["spec"]["volumes"]
        assert vols[0]["configMap"]["name"] == "app-config"

    def test_secret_volume(self):
        with manifest() as m:
            with Deployment("app"):
                SecretVolume("certs", "tls-certs")
                with Container("app", image="app:v1"):
                    VolumeMount("/certs", "certs", read_only=True)

        dep = m.to_dicts()[0]
        vols = dep["spec"]["template"]["spec"]["volumes"]
        assert vols[0]["secret"]["secretName"] == "tls-certs"


# ─────────────────────────────────────────────
# NAMESPACE
# ─────────────────────────────────────────────
class TestNamespace:
    def test_namespace(self):
        with manifest() as m:
            Namespace("production")

        ns = m.to_dicts()[0]
        assert ns["kind"] == "Namespace"
        assert ns["metadata"]["name"] == "production"


# ─────────────────────────────────────────────
# MANIFEST
# ─────────────────────────────────────────────
class TestManifest:
    def test_multiple_resources(self):
        with manifest() as m:
            Namespace("my-app")
            with Deployment("api"):
                with Container("api", image="api:v1"):
                    Port(8080)
                Service(port=8080)
            with ConfigMap("config"):
                Data("key", "val")

        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        assert "Namespace" in kinds
        assert "Deployment" in kinds
        assert "Service" in kinds
        assert "ConfigMap" in kinds

    def test_to_yaml(self):
        with manifest() as m:
            with Deployment("web"):
                with Container("web", image="nginx"):
                    Port(80)

        yaml_str = m.to_yaml()
        assert "kind: Deployment" in yaml_str
        assert "image: nginx" in yaml_str

    def test_nested_manifest_isolation(self):
        """Nested manifests do not affect each other."""
        with manifest() as outer:
            Namespace("outer")
            with manifest() as inner:
                Namespace("inner")
            assert len(inner.to_dicts()) == 1
        assert len(outer.to_dicts()) == 1


# ─────────────────────────────────────────────
# FULL STACK — PostgreSQL example
# ─────────────────────────────────────────────
class TestFullStack:
    def test_postgresql_full(self):
        """Full PostgreSQL deployment — demonstrates the power of bow."""
        with manifest() as m:
            with Secret("pg-credentials"):
                Data("POSTGRES_USER", "admin")
                Data("POSTGRES_PASSWORD", "s3cret")

            with ConfigMap("pg-config"):
                Data("POSTGRES_DB", "appdb")
                Data("PGDATA", "/var/lib/postgresql/data/pgdata")

            with Deployment("postgresql", replicas=1):
                ConfigMapVolume("config", "pg-config")
                SecretVolume("creds", "pg-credentials")

                with Container("postgresql", image="postgres:16"):
                    Port(5432, name="pg")
                    EnvVar("POSTGRES_DB", configmap_ref="pg-config",
                           configmap_key="POSTGRES_DB")
                    EnvVar("POSTGRES_USER", secret_ref="pg-credentials",
                           secret_key="POSTGRES_USER")
                    EnvVar("POSTGRES_PASSWORD", secret_ref="pg-credentials",
                           secret_key="POSTGRES_PASSWORD")
                    Resources(cpu="250m", memory="256Mi",
                              limits_cpu="500m", limits_memory="512Mi")
                    VolumeMount("/var/lib/postgresql/data", "pgdata")
                    Probe("liveness", tcp_socket={"port": 5432},
                          initial_delay=30, period=10)
                    Probe("readiness", exec_command=[
                        "pg_isready", "-U", "admin"
                    ], initial_delay=5, period=5)

                PersistentVolumeClaim("pgdata", size="50Gi")
                Service(port=5432)

        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        assert kinds == [
            "Secret",
            "ConfigMap",
            "PersistentVolumeClaim",
            "Deployment",
            "Service",
        ]

        # YAML render
        yaml_str = m.to_yaml()
        assert "---" in yaml_str
        # Should be parseable
        parsed = list(yaml.safe_load_all(yaml_str))
        assert len(parsed) == 5
