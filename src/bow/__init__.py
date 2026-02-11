"""
bow — Pythonic Kubernetes DSL.

As powerful as Helm, as easy as Pulumi, as readable as Python.
"""

from bow.core.manifest import manifest, Manifest
from bow.core.resource import Resource, set_tracking
from bow.core.resources import (
    # with resources
    Namespace,
    Deployment,
    StatefulSet,
    CronJob,
    Container,
    Service,
    ConfigMap,
    Secret,
    Ingress,
    PersistentVolumeClaim,
    # leaf nodes
    Port,
    EnvVar,
    Resources,
    VolumeMount,
    Probe,
    ServicePort,
    Data,
    IngressRule,
    EmptyDirVolume,
    ConfigMapVolume,
    SecretVolume,
)

__version__ = "0.1.0"

__all__ = [
    # core
    "manifest",
    "Manifest",
    "Resource",
    "set_tracking",
    # with resources
    "Namespace",
    "Deployment",
    "StatefulSet",
    "CronJob",
    "Container",
    "Service",
    "ConfigMap",
    "Secret",
    "Ingress",
    "PersistentVolumeClaim",
    # leaf nodes
    "Port",
    "EnvVar",
    "Resources",
    "VolumeMount",
    "Probe",
    "ServicePort",
    "Data",
    "IngressRule",
    "EmptyDirVolume",
    "ConfigMapVolume",
    "SecretVolume",
]
