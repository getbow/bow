# AGENTS.md — Bow

## Project Description

Bow is a Pythonic Kubernetes DSL. It applies Tagflow's `contextlib` pattern to Kubernetes resources. As powerful as Helm, as easy as Pulumi, as readable as Python.

Users operate at three layers:

- **Layer 1 — CLI one-liner:** `bow up postgresql --set storage=50Gi`
- **Layer 2 — YAML Stack:** `bow up -f stack.yaml -f values.prod.yaml` (no Python knowledge required)
- **Layer 3 — Python Chart development:** Chart authors define components with `contextlib`

---

## Architecture

### Context Manager Stack

Inspired by Tagflow. Operates on a thread-local stack. `with Resource()` pushes to the stack, pops when the block ends. Leaf nodes find their parent via `_current()`.

```
with Deployment("api"):              # push → stack
    with Container("api", "img"):    # push → stack
        Port(80)                     # leaf → finds Container via _current()
        EnvVar("DB", "x")           # leaf
        Resources(cpu="250m")        # leaf
        VolumeMount("/data", "vol")  # leaf
    Service(port=80)                 # leaf (simple mode)
    with Service(type="NodePort"):   # push → stack (complex mode)
        ServicePort(80, name="http") # leaf
        ServicePort(443)             # leaf
```

**Core rule:** If it can accept children, use `with`; if it's a leaf node, use a plain function call.

### Resource Table

| Resource | Mode | Parent | Description |
|----------|------|--------|-------------|
| Namespace | with | top-level | |
| Deployment | with | top-level | |
| StatefulSet | with | top-level | |
| CronJob | with | top-level | |
| Container | with | Deployment, StatefulSet, CronJob | |
| Service | both | Deployment, StatefulSet | Simple: leaf / Multi-port: with |
| ConfigMap | with | top-level | Populated with `Data()` leaf |
| Secret | with | top-level | Populated with `Data()` leaf |
| Ingress | with | top-level | Parametric, populated with `IngressRule()` leaf |
| PVC | leaf | Deployment, StatefulSet | |
| Port | leaf | Container | |
| EnvVar | leaf | Container | |
| Resources | leaf | Container | |
| VolumeMount | leaf | Container | |
| Probe | leaf | Container | |
| Data | leaf | ConfigMap, Secret | |
| ServicePort | leaf | Service | |
| IngressRule | leaf | Ingress | |

---

## Chart System

### Each chart is a pip package

```
bow-postgresql/
├── pyproject.toml
├── src/bow_postgresql/
│   ├── __init__.py         # PostgreSQLChart export
│   ├── chart.py            # Chart class, render logic
│   └── defaults.yaml       # Default values
```

### Dependency management is delegated to pip

```toml
# bow-redmine/pyproject.toml
[project]
name = "bow-redmine"
version = "5.1.0"
dependencies = [
    "bow>=0.1.0",
    "bow-postgresql>=16.0.0",
]
```

Semver is strictly enforced.

### Chart discovery is done via entry_points

```toml
[project.entry-points."bow.charts"]
postgresql = "bow_postgresql:PostgreSQLChart"
```

The `bow up postgresql` command finds the `postgresql` key from entry_points and loads the corresponding Chart class.

### Dependency deploy is declared declaratively

```python
class RedmineChart(Chart):
    requires = [
        ChartDep("postgresql", deploy=True, condition="postgresql.enabled"),
    ]
```

A chart does not deploy its own dependencies. It declares them in metadata; the CLI resolves them.

---

## YAML Stack Format

Enables component architecture without Python knowledge.

```yaml
apiVersion: bow.io/v1
kind: Stack
metadata:
  name: my-project
  namespace: my-project

components:
  - chart: postgresql
    name: main-db
    values:
      version: "16"
      storage: 50Gi

  - chart: redis
    name: cache

  - chart: redmine
    name: redmine
    values:
      postgresql:
        enabled: false
        external_host: "${main-db.host}"
```

Raw K8s resources cannot be written in a stack without a chart. Only chart components are used.

### Component references

Components reference each other using the `${component_name.host}` syntax. Kept simple for now, will be expanded later.

### Environment overlay

Multiple `-f` files are deep merged. Precedence order (low to high):

```
defaults.yaml (within chart) → -f values.yaml → -f values.prod.yaml → --set key=val
```

---

## CLI

```bash
# Deploy
bow up <chart>                                # deploy with default values
bow up <chart> --set key=val                  # value override
bow up <chart> -f values.yaml                 # values from file
bow up <chart> -f values.yaml --set key=val   # both combined
bow up <chart> -n <namespace>                 # specify namespace
bow up <chart> -n <ns> --create-namespace     # create namespace if missing
bow up -f stack.yaml                          # stack deploy
bow up -f stack.yaml -f values.prod.yaml      # stack + overlay

# Debug
bow template <chart> [flags]    # generate YAML, don't apply

# Info
bow list                        # list installed charts
bow inspect <chart>             # detail + dependency tree + defaults

# Phase 2
bow diff <chart> [flags]        # diff with cluster state
bow down <chart> -n <ns>        # delete
```

### Namespace behavior

- If `-n` is given, deploys to that namespace
- With `--create-namespace`, creates the namespace if it doesn't exist
- If no flag is given, uses the active kubectl context namespace

### Apply mechanism

- Phase 1: render → `kubectl apply -f -`
- Phase 2: render → Kubernetes API directly

---

## State and Tracking

Relies on Kubernetes (stateless). Additionally, tracking labels are added to each resource:

```yaml
metadata:
  labels:
    bow.io/managed-by: bow
    bow.io/chart: redmine
    bow.io/version: 5.1.0
    bow.io/stack: my-project
```

---

## Project Structure

```
bow/
├── pyproject.toml
├── AGENTS.md
├── src/bow/
│   ├── __init__.py
│   ├── core/
│   │   ├── stack.py             # thread-local context stack
│   │   ├── resource.py          # base Resource class
│   │   ├── resources.py         # all concrete resources
│   │   └── manifest.py          # manifest collector + YAML render
│   ├── chart/
│   │   ├── base.py              # Chart base class
│   │   ├── dependency.py        # ChartDep definition + resolver
│   │   ├── registry.py          # entry_points discovery
│   │   └── values.py            # values deep merge logic
│   ├── stack/
│   │   ├── parser.py            # stack.yaml parser
│   │   ├── refs.py              # ${ref} resolver
│   │   └── merger.py            # multi-file deep merge
│   └── cli/
│       ├── __init__.py          # click app
│       ├── up.py                # bow up
│       ├── template.py          # bow template
│       ├── list_cmd.py          # bow list
│       └── inspect_cmd.py       # bow inspect
├── examples/
│   ├── simple-deploy/
│   ├── stack-example/
│   └── chart-dev-example/
└── tests/
```

---

## Development Phases

| Phase | Scope | Output |
|-------|-------|--------|
| 1 | `core/` — stack, resource, resources, manifest | `with Deployment()` works, generates YAML |
| 2 | `cli/` — `bow template` | YAML can be viewed from CLI |
| 3 | `chart/` — base, registry, values | Chart package can be written, discovered |
| 4 | `cli/` — `bow up` | Deploy works with `kubectl apply` |
| 5 | `stack/` — parser, merger | `stack.yaml` parse and multi-file merge works |
| 6 | Example chart packages | bow-postgresql, bow-redis, bow-redmine |
| 7 | `stack/` — refs | `${component.host}` references work |
| 8 | `cli/` — list, inspect | Info commands work |

---

## Rules and Constraints

- Direct usage within Python is not done unless specifically requested. The entry point is always the CLI.
- Charts are standard Python packages. Versioning and dependency management is done via pip/pyproject.toml.
- Default values are kept in YAML format.
- Semver is strictly enforced.
- Raw K8s resource definitions are not allowed in stack files without a chart.
- Tracking labels (`bow.io/*`) are added to every deployed resource.
