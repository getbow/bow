# bow-cli

Pythonic Kubernetes DSL — As powerful as Helm, as easy as Pulumi, as readable as Python.

```python
with Deployment("api", replicas=3):
    with Container("api", image="myorg/api:v2"):
        Port(8080)
        EnvVar("DB_HOST", "postgresql")
        Resources(cpu="250m", memory="256Mi")
        Probe("readiness", http_get={"path": "/health", "port": 8080})
    Service(port=8080)
```

## Installation

```bash
pip install bow-cli
```

## Quick Start

### Deploy with CLI

```bash
# Single chart
bow up postgresql
bow up postgresql --set replicas=3 --set storage=50Gi
bow up postgresql -f values.yaml

# With stack file
bow up -f stack.yaml
bow up -f stack.yaml -f values.prod.yaml

# YAML preview (without applying)
bow template postgresql --set metrics.enabled=true
```

### Stack file

```yaml
# stack.yaml
apiVersion: bow.io/v1
kind: Stack
metadata:
  name: my-project
  namespace: my-project

components:
  - chart: postgresql
    name: db
    values:
      database: myapp
      storage: 50Gi

  - chart: redis
    name: cache
    values:
      storage: 5Gi

  - chart: redmine
    name: redmine
    values:
      postgresql:
        enabled: false
        name: "${db.host}"
```

### Environment overlay

```yaml
# values.prod.yaml
components:
  db:
    values:
      replicas: 3
      storage: 200Gi
  redmine:
    values:
      replicas: 5
      ingress:
        enabled: true
        host: redmine.example.com
        tls: true
```

```bash
bow up -f stack.yaml -f values.prod.yaml
```

## Three Usage Layers

### Layer 1: CLI one-liner

```bash
bow up postgresql --set storage=50Gi
```

### Layer 2: YAML Stack

Declarative component architecture without any Python knowledge:

```bash
bow up -f stack.yaml -f values.prod.yaml --set components.db.values.replicas=5
```

### Layer 3: Python Chart Development

Chart authors define reusable components using `contextlib`:

```python
from contextlib import contextmanager
from bow.chart.base import Chart
from bow.core.resources import *

@contextmanager
def my_container(name, image, port=8080):
    with Container(name, image=image):
        Port(port, name="http")
        Probe("readiness", http_get={"path": "/health", "port": port})
        yield  # can be extended inside the with block

class MyChart(Chart):
    name = "myapp"
    version = "1.0.0"

    def render(self, values):
        with Deployment(values["name"], replicas=values.get("replicas", 1)):
            with my_container(values["name"], values["image"]):
                EnvVar("DB_HOST", values.get("db_host", "localhost"))
            Service(port=8080)
```

## Resource Reference

### with (context manager) — can have children

```python
with Deployment("api", replicas=3):          # Pod spec parent
    with Container("api", image="app:v1"):   # Leaf parent
        ...
    with Service(type="NodePort"):           # Multi-port mode
        ServicePort(80, name="http")
        ServicePort(443, name="https")

with StatefulSet("db", replicas=3):          # StatefulSet
    ...

with ConfigMap("cfg"):                       # Key-value store
    Data("key", "value")

with Secret("creds"):                        # Encoded data
    Data("password", "s3cret")

with Ingress("ing", host="app.example.com"): # Parametric
    IngressRule("/", "web", 80)
    IngressRule("/api", "api", 8080)

with CronJob("backup", schedule="0 2 * * *"):
    with Container("backup", image="backup:v1"):
        ...
```

### Leaf — no children, plain function call

```python
Port(8080, name="http")
EnvVar("DB_HOST", "localhost")
EnvVar("PASSWORD", secret_ref="my-secret", secret_key="pass")
Resources(cpu="250m", memory="256Mi", limits_cpu="500m", limits_memory="512Mi")
VolumeMount("/data", "my-vol", read_only=True)
Probe("liveness", http_get={"path": "/health", "port": 8080})
Service(port=80)                              # Simple mode (leaf)
Data("key", "value")                          # Inside ConfigMap/Secret
IngressRule("/", "web", 80)                   # Inside Ingress
PersistentVolumeClaim("data", size="50Gi")
EmptyDirVolume("tmp")
ConfigMapVolume("cfg", "my-config")
SecretVolume("certs", "tls-certs")
```

## Chart Development

Each chart is a pip package:

```
bow-myapp/
├── pyproject.toml
├── src/bow_myapp/
│   ├── __init__.py      # MyChart class
│   └── defaults.yaml    # Default values
```

```toml
# pyproject.toml
[project]
name = "bow-myapp"
version = "1.0.0"
dependencies = ["bow-cli>=0.1.0"]

[project.entry-points."bow.charts"]
myapp = "bow_myapp:MyChart"
```

### Dependency

```toml
# bow-redmine/pyproject.toml
dependencies = [
    "bow-cli>=0.1.0",
    "bow-postgresql>=16.0.0",
]
```

```python
from bow.chart.dependency import ChartDep

class RedmineChart(Chart):
    requires = [
        ChartDep("postgresql", deploy=True, condition="postgresql.enabled"),
    ]
```

## CLI Commands

```bash
bow up <chart> [flags]       # Deploy
bow template <chart> [flags] # YAML preview
bow list                     # Installed charts
bow inspect <chart>          # Chart details + defaults
```

### Flags

| Flag | Description |
|------|-------------|
| `-f <file>` | Values or stack file (multiple allowed) |
| `--set key=val` | Value override |
| `-n <namespace>` | Kubernetes namespace |
| `--create-namespace` | Create namespace if it doesn't exist |
| `--dry-run` | kubectl dry-run |
| `-o <file>` | Output file (template) |

### Value precedence

```
defaults.yaml → -f values.yaml → -f values.prod.yaml → --set key=val
```

## License

MIT
