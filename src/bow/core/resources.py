"""
bow.core.resources — Concrete Kubernetes resources.

Rule: If it can have children, use `with`; if it's a leaf, use a plain function call.

with: Namespace, Deployment, StatefulSet, CronJob, Container,
      Service (complex), ConfigMap, Secret, Ingress
leaf: Port, EnvVar, Resources, VolumeMount, Probe, Data,
      ServicePort, IngressRule, PVC, EmptyDirVolume,
      ConfigMapVolume, SecretVolume, Service (simple)
"""

from __future__ import annotations

from typing import Any
import base64

from bow.core.resource import Resource
from bow.core.stack import _current, _push, _pop


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NAMESPACE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Namespace(Resource):
    _kind = "Namespace"
    _api_version = "v1"

    def render(self) -> dict[str, Any]:
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": self.metadata,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONTAINER — Not a K8s resource, but a pod spec child
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Container:
    """Pod spec container. Used with the `with` block.

    Leaf nodes (Port, EnvVar, etc.) reach the Container
    instance via _current() and add directly to its lists.
    """

    def __init__(self, name: str, image: str, **kwargs: Any):
        self.name = name
        self.image = image
        self.ports: list[dict] = []
        self.env: list[dict] = []
        self.resources: dict = {}
        self.volume_mounts: list[dict] = []
        self.probes: dict = {}
        self.command: list[str] | None = kwargs.get("command")
        self.args: list[str] | None = kwargs.get("args")
        self.image_pull_policy: str | None = kwargs.get("image_pull_policy")

        # Register self with parent
        parent = _current()
        if parent is not None:
            parent._adopt(self)

    def __enter__(self):
        _push(self)
        return self

    def __exit__(self, *exc: Any) -> bool:
        _pop()
        return False

    def _adopt(self, child: Any) -> None:
        """Container has no children; leaves manipulate it directly."""
        pass

    def render(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "name": self.name,
            "image": self.image,
        }
        if self.command:
            spec["command"] = self.command
        if self.args:
            spec["args"] = self.args
        if self.image_pull_policy:
            spec["imagePullPolicy"] = self.image_pull_policy
        if self.ports:
            spec["ports"] = self.ports
        if self.env:
            spec["env"] = self.env
        if self.resources:
            spec["resources"] = self.resources
        if self.volume_mounts:
            spec["volumeMounts"] = self.volume_mounts
        for key in ("livenessProbe", "readinessProbe", "startupProbe"):
            if key in self.probes:
                spec[key] = self.probes[key]
        return spec


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONTAINER LEAF NODES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def Port(
    container_port: int,
    name: str | None = None,
    protocol: str = "TCP",
) -> None:
    """Container port definition."""
    parent = _current()
    if not isinstance(parent, Container):
        raise TypeError("Port() must be inside a Container context")
    p: dict[str, Any] = {"containerPort": container_port, "protocol": protocol}
    if name:
        p["name"] = name
    parent.ports.append(p)


def EnvVar(
    name: str,
    value: str | None = None,
    *,
    secret_ref: str | None = None,
    secret_key: str | None = None,
    configmap_ref: str | None = None,
    configmap_key: str | None = None,
    field_ref: str | None = None,
) -> None:
    """Container environment variable."""
    parent = _current()
    if not isinstance(parent, Container):
        raise TypeError("EnvVar() must be inside a Container context")

    entry: dict[str, Any] = {"name": name}

    if secret_ref:
        entry["valueFrom"] = {
            "secretKeyRef": {
                "name": secret_ref,
                "key": secret_key or name,
            }
        }
    elif configmap_ref:
        entry["valueFrom"] = {
            "configMapKeyRef": {
                "name": configmap_ref,
                "key": configmap_key or name,
            }
        }
    elif field_ref:
        entry["valueFrom"] = {"fieldRef": {"fieldPath": field_ref}}
    else:
        entry["value"] = str(value) if value is not None else ""

    parent.env.append(entry)


def Resources(
    cpu: str | None = None,
    memory: str | None = None,
    limits_cpu: str | None = None,
    limits_memory: str | None = None,
) -> None:
    """Container resource requests/limits."""
    parent = _current()
    if not isinstance(parent, Container):
        raise TypeError("Resources() must be inside a Container context")

    r: dict[str, dict[str, str]] = {}
    if cpu or memory:
        r["requests"] = {}
        if cpu:
            r["requests"]["cpu"] = cpu
        if memory:
            r["requests"]["memory"] = memory
    if limits_cpu or limits_memory:
        r["limits"] = {}
        if limits_cpu:
            r["limits"]["cpu"] = limits_cpu
        if limits_memory:
            r["limits"]["memory"] = limits_memory
    parent.resources = r


def VolumeMount(
    mount_path: str,
    name: str,
    sub_path: str | None = None,
    read_only: bool = False,
) -> None:
    """Container volume mount."""
    parent = _current()
    if not isinstance(parent, Container):
        raise TypeError("VolumeMount() must be inside a Container context")
    m: dict[str, Any] = {"name": name, "mountPath": mount_path}
    if sub_path:
        m["subPath"] = sub_path
    if read_only:
        m["readOnly"] = True
    parent.volume_mounts.append(m)


def Probe(
    probe_type: str,
    *,
    http_get: dict | None = None,
    tcp_socket: dict | None = None,
    exec_command: list[str] | None = None,
    initial_delay: int = 0,
    period: int = 10,
    timeout: int = 1,
    failure_threshold: int = 3,
) -> None:
    """Container probe (liveness/readiness/startup)."""
    parent = _current()
    if not isinstance(parent, Container):
        raise TypeError("Probe() must be inside a Container context")

    if probe_type not in ("liveness", "readiness", "startup"):
        raise ValueError(f"probe_type must be liveness/readiness/startup, got {probe_type}")

    probe: dict[str, Any] = {
        "initialDelaySeconds": initial_delay,
        "periodSeconds": period,
        "timeoutSeconds": timeout,
        "failureThreshold": failure_threshold,
    }
    if http_get:
        probe["httpGet"] = http_get
    elif tcp_socket:
        probe["tcpSocket"] = tcp_socket
    elif exec_command:
        probe["exec"] = {"command": exec_command}

    parent.probes[f"{probe_type}Probe"] = probe


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PVC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PersistentVolumeClaim(Resource):
    _kind = "PersistentVolumeClaim"
    _api_version = "v1"

    def __init__(
        self,
        name: str,
        size: str = "10Gi",
        access_modes: list[str] | None = None,
        storage_class: str | None = None,
        **kwargs: Any,
    ):
        self.size = size
        self.access_modes = access_modes or ["ReadWriteOnce"]
        self.storage_class = storage_class
        self.claim_name = name
        super().__init__(name, **kwargs)

    def render(self) -> dict[str, Any]:
        if self.enabled is False:
            return None  # Render empty if disabled
        
        spec: dict[str, Any] = {
            "accessModes": self.access_modes,
            "resources": {"requests": {"storage": self.size}},
        }
        if self.storage_class:
            spec["storageClassName"] = self.storage_class
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": {"name": self.claim_name},
            "spec": spec,
        }

    def render_template(self) -> dict[str, Any]:
        """StatefulSet volumeClaimTemplate format."""
        spec: dict[str, Any] = {
            "accessModes": self.access_modes,
            "resources": {"requests": {"storage": self.size}},
        }
        if self.storage_class:
            spec["storageClassName"] = self.storage_class
        return {
            "metadata": {"name": self.claim_name},
            "spec": spec,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VOLUME HELPERS — Deployment/StatefulSet leaves
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _add_volume(vol: dict[str, Any]) -> None:
    """Add volume to active parent."""
    parent = _current()
    if hasattr(parent, "volumes"):
        parent.volumes.append(vol)
    else:
        raise TypeError(f"Cannot add volume inside {type(parent).__name__}")


def EmptyDirVolume(name: str, medium: str | None = None) -> None:
    """EmptyDir volume."""
    vol: dict[str, Any] = {"name": name, "emptyDir": {}}
    if medium:
        vol["emptyDir"]["medium"] = medium
    _add_volume(vol)


def ConfigMapVolume(name: str, configmap_name: str) -> None:
    """ConfigMap volume."""
    _add_volume({"name": name, "configMap": {"name": configmap_name}})


def SecretVolume(name: str, secret_name: str) -> None:
    """Secret volume."""
    _add_volume({"name": name, "secret": {"secretName": secret_name}})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEPLOYMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Deployment(Resource):
    _kind = "Deployment"
    _api_version = "apps/v1"

    def __init__(
        self,
        name: str,
        replicas: int = 1,
        labels: dict | None = None,
        **kwargs: Any,
    ):
        self.replicas = replicas
        self.labels = labels or {"app": name}
        self.containers: list[Container] = []
        self.init_containers: list[Container] = []
        self.volumes: list[dict] = []
        self.services: list[Service] = []
        self.pvcs: list[PersistentVolumeClaim] = []
        super().__init__(name, labels=self.labels, **kwargs)

    def _adopt(self, child: Any) -> None:
        if isinstance(child, Container):
            self.containers.append(child)
        elif isinstance(child, Service):
            if not child.selector:
                child.selector = dict(self.labels)
            self.services.append(child)
        elif isinstance(child, PersistentVolumeClaim):
            if child.enabled is False:
                return
            self.pvcs.append(child)
            self.volumes.append({
                "name": child.claim_name,
                "persistentVolumeClaim": {"claimName": child.claim_name},
            })
        else:
            super()._adopt(child)

    def render(self) -> dict[str, Any]:
        pod_spec: dict[str, Any] = {
            "containers": [c.render() for c in self.containers],
        }
        if self.init_containers:
            pod_spec["initContainers"] = [c.render() for c in self.init_containers]
        if self.volumes:
            pod_spec["volumes"] = self.volumes

        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": self.metadata,
            "spec": {
                "replicas": self.replicas,
                "selector": {"matchLabels": self.labels},
                "template": {
                    "metadata": {"labels": self.labels},
                    "spec": pod_spec,
                },
            },
        }

    def render_all(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for pvc in self.pvcs:
            doc = pvc.render()
            if doc is not None:
                docs.append(doc)
        docs.append(self.render())
        for svc in self.services:
            docs.append(svc.render())
        return docs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATEFULSET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class StatefulSet(Resource):
    _kind = "StatefulSet"
    _api_version = "apps/v1"

    def __init__(
        self,
        name: str,
        replicas: int = 1,
        service_name: str | None = None,
        labels: dict | None = None,
        **kwargs: Any,
    ):
        self.replicas = replicas
        self.service_name = service_name or name
        self.labels = labels or {"app": name}
        self.containers: list[Container] = []
        self.volumes: list[dict] = []
        self.volume_claim_templates: list[dict] = []
        self.services: list[Service] = []
        super().__init__(name, labels=self.labels, **kwargs)

    def _adopt(self, child: Any) -> None:
        if isinstance(child, Container):
            self.containers.append(child)
        elif isinstance(child, Service):
            if not child.selector:
                child.selector = dict(self.labels)
            self.services.append(child)
        elif isinstance(child, PersistentVolumeClaim):
            if child.enabled is False:
                return
            self.volume_claim_templates.append(child.render_template())
        else:
            super()._adopt(child)

    def render(self) -> dict[str, Any]:
        pod_spec: dict[str, Any] = {
            "containers": [c.render() for c in self.containers],
        }
        if self.volumes:
            pod_spec["volumes"] = self.volumes

        spec: dict[str, Any] = {
            "replicas": self.replicas,
            "serviceName": self.service_name,
            "selector": {"matchLabels": self.labels},
            "template": {
                "metadata": {"labels": self.labels},
                "spec": pod_spec,
            },
        }
        if self.volume_claim_templates:
            spec["volumeClaimTemplates"] = self.volume_claim_templates

        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": self.metadata,
            "spec": spec,
        }

    def render_all(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        docs.append(self.render())
        for svc in self.services:
            docs.append(svc.render())
        return docs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SERVICE — both leaf and with
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ServicePort:
    """Service port definition. Used as a leaf inside a Service context."""

    def __init__(
        self,
        port: int,
        target_port: int | None = None,
        name: str | None = None,
        protocol: str = "TCP",
        node_port: int | None = None,
    ):
        spec: dict[str, Any] = {
            "port": port,
            "targetPort": target_port or port,
            "protocol": protocol,
        }
        if name:
            spec["name"] = name
        if node_port:
            spec["nodePort"] = node_port

        parent = _current()
        if isinstance(parent, Service):
            parent.ports.append(spec)
        else:
            raise TypeError("ServicePort() must be inside a Service context")


class Service(Resource):
    """Kubernetes Service. Can be used in simple or complex mode.

    Simple (leaf)::

        Service(port=80)

    Complex (with)::

        with Service(type="NodePort"):
            ServicePort(80, name="http")
            ServicePort(443, name="https")
    """

    _kind = "Service"
    _api_version = "v1"

    def __init__(
        self,
        port: int | None = None,
        target_port: int | None = None,
        name: str | None = None,
        type: str = "ClusterIP",
        **kwargs: Any,
    ):
        self.type = type
        self.selector: dict = kwargs.pop("selector", {})
        self.ports: list[dict] = []

        # Leaf mode: if port is provided, add it immediately
        if port is not None:
            p: dict[str, Any] = {
                "port": port,
                "targetPort": target_port or port,
            }
            self.ports.append(p)

        # Name: explicit or from parent
        parent = _current()
        svc_name = name or (parent.name if parent else "unnamed")
        super().__init__(svc_name, **kwargs)

    def _adopt(self, child: Any) -> None:
        pass  # ServicePort adds directly to self.ports

    def render(self) -> dict[str, Any]:
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": {"name": self.metadata["name"]},
            "spec": {
                "type": self.type,
                "selector": self.selector,
                "ports": self.ports,
            },
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGMAP — both leaf and with
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ConfigMap(Resource):
    _kind = "ConfigMap"
    _api_version = "v1"

    def __init__(self, name: str, data: dict[str, str] | None = None, **kwargs: Any):
        self.data: dict[str, str] = dict(data) if data else {}
        super().__init__(name, **kwargs)

    def _adopt(self, child: Any) -> None:
        pass

    def render(self) -> dict[str, Any]:
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": {"name": self.metadata["name"]},
            "data": self.data,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECRET — both leaf and with
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Secret(Resource):
    _kind = "Secret"
    _api_version = "v1"

    def __init__(
        self,
        name: str,
        data: dict[str, str] | None = None,
        string_data: dict[str, str] | None = None,
        type: str = "Opaque",
        **kwargs: Any,
    ):
        self.data: dict[str, str] = dict(data) if data else {}
        self.string_data: dict[str, str] = dict(string_data) if string_data else {}
        self.secret_type = type
        super().__init__(name, **kwargs)

    def _adopt(self, child: Any) -> None:
        pass

    def render(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": {"name": self.metadata["name"]},
            "type": self.secret_type,
        }
        if self.data:
            doc["data"] = {
                k: base64.b64encode(v.encode()).decode()
                for k, v in self.data.items()
            }
        if self.string_data:
            doc["stringData"] = self.string_data
        return doc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA — ConfigMap/Secret leaf
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def Data(key: str, value: str) -> None:
    """Add a key-value pair to a ConfigMap or Secret."""
    parent = _current()
    if isinstance(parent, ConfigMap):
        parent.data[key] = value
    elif isinstance(parent, Secret):
        parent.data[key] = value
    else:
        raise TypeError("Data() must be inside a ConfigMap or Secret context")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INGRESS — parametric with
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Ingress(Resource):
    _kind = "Ingress"
    _api_version = "networking.k8s.io/v1"

    def __init__(
        self,
        name: str,
        host: str | None = None,
        tls: bool = False,
        tls_secret: str | None = None,
        ingress_class: str = "nginx",
        annotations: dict | None = None,
        **kwargs: Any,
    ):
        self.host = host
        self.tls = tls
        self.tls_secret = tls_secret or (f"{name}-tls" if tls else None)
        self.ingress_class = ingress_class
        self.rules: list[dict] = []

        ann = dict(annotations or {})
        super().__init__(name, annotations=ann, **kwargs)

    def _adopt(self, child: Any) -> None:
        pass

    def render(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "ingressClassName": self.ingress_class,
            "rules": self.rules,
        }
        if self.tls and self.host:
            spec["tls"] = [{
                "hosts": [self.host],
                "secretName": self.tls_secret,
            }]
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": self.metadata,
            "spec": spec,
        }


def IngressRule(
    path: str,
    service_name: str,
    service_port: int,
    host: str | None = None,
    path_type: str = "Prefix",
) -> None:
    """Ingress rule. Leaf node."""
    parent = _current()
    if not isinstance(parent, Ingress):
        raise TypeError("IngressRule() must be inside an Ingress context")

    rule_host = host or parent.host
    backend = {
        "service": {
            "name": service_name,
            "port": {"number": service_port},
        }
    }
    path_spec = {
        "path": path,
        "pathType": path_type,
        "backend": backend,
    }

    # If a rule for the same host already exists, append the path
    for existing in parent.rules:
        if existing.get("host") == rule_host:
            existing["http"]["paths"].append(path_spec)
            return

    rule: dict[str, Any] = {
        "http": {"paths": [path_spec]},
    }
    if rule_host:
        rule["host"] = rule_host
    parent.rules.append(rule)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRONJOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class CronJob(Resource):
    _kind = "CronJob"
    _api_version = "batch/v1"

    def __init__(
        self,
        name: str,
        schedule: str,
        restart_policy: str = "OnFailure",
        **kwargs: Any,
    ):
        self.schedule = schedule
        self.restart_policy = restart_policy
        self.containers: list[Container] = []
        self.volumes: list[dict] = []
        super().__init__(name, **kwargs)

    def _adopt(self, child: Any) -> None:
        if isinstance(child, Container):
            self.containers.append(child)
        else:
            super()._adopt(child)

    def render(self) -> dict[str, Any]:
        pod_spec: dict[str, Any] = {
            "containers": [c.render() for c in self.containers],
            "restartPolicy": self.restart_policy,
        }
        if self.volumes:
            pod_spec["volumes"] = self.volumes

        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": self.metadata,
            "spec": {
                "schedule": self.schedule,
                "jobTemplate": {
                    "spec": {
                        "template": {
                            "spec": pod_spec,
                        }
                    }
                },
            },
        }
