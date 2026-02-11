<!--
  Sync Impact Report
  ==================
  Version change: 0.0.0 (unfilled template) → 1.0.0
  Modified principles: N/A (initial adoption)
  Added sections:
    - 6 Core Principles (I–VI)
    - Technology & Constraints
    - Development Workflow
    - Governance
  Removed sections: None
  Templates requiring updates:
    - .specify/templates/plan-template.md        ✅ compatible (generic)
    - .specify/templates/spec-template.md         ✅ compatible (generic)
    - .specify/templates/tasks-template.md        ✅ compatible (generic)
    - .specify/templates/checklist-template.md    ✅ compatible (generic)
    - .specify/templates/agent-file-template.md   ✅ compatible (generic)
  Follow-up TODOs: None
-->

# Bow Constitution

## Core Principles

### I. Explicit is Better Than Implicit

Every behavior MUST be visible and traceable. No hidden state,
no magic registration, no implicit side effects.

- Resources declare themselves via `with` blocks or direct calls;
  parent-child relationships are explicit through the thread-local
  stack, never inferred.
- Tracking labels (`bow.io/managed-by`, `bow.io/chart`,
  `bow.io/version`, `bow.io/stack`) MUST be added to every
  deployed resource. The cluster state is the source of truth.
- Configuration flows through a single, predictable merge chain:
  `defaults.yaml → -f values.yaml → -f values.prod.yaml → --set`.
  No environment variable magic, no implicit config discovery.

**Rationale:** PEP 20 — "Explicit is better than implicit."
Kubernetes debugging is hard enough without hidden plumbing.

### II. CLI-First, Python-Second

The entry point is always the CLI. Python code is for chart
authors, not end users.

- All user-facing operations MUST go through `bow up`,
  `bow template`, `bow list`, `bow inspect`, or future CLI
  commands. Direct Python API usage is not a supported workflow
  unless explicitly requested.
- CLI output MUST be deterministic YAML (for `template`) or
  clear human-readable text (for `list`, `inspect`).
- Click is the CLI framework. Commands are thin; business logic
  lives in `chart/`, `core/`, and `stack/`.

**Rationale:** PEP 20 — "There should be one— and preferably
only one —obvious way to do it." One entry point, one way in.

### III. Composition Over Configuration

Resources compose through Python's `with` statement. No YAML
templating engine, no Go templates, no Jinja.

- If a resource can accept children, use `with`. If it is a leaf
  node, use a plain function call. This rule is absolute.
- Charts are `@contextmanager` functions that yield composable
  resource trees. Components (e.g., `pg_container()`,
  `redis_container()`) MUST be reusable both inside and outside
  their parent chart.
- YAML Stack files compose charts declaratively. Raw K8s resource
  definitions are NOT allowed in stack files — only chart
  components.

**Rationale:** PEP 20 — "Simple is better than complex."
Python's context manager protocol replaces an entire templating
engine with stdlib.

### IV. Delegate, Don't Reinvent

Leverage existing tools for what they do best. Bow's job is the
DSL layer, not the entire ecosystem.

- Dependency management is pip and `pyproject.toml`. Bow MUST NOT
  implement its own package resolver.
- Chart discovery uses Python `entry_points`. No custom registry,
  no central server.
- Cluster apply uses `kubectl apply -f -` (Phase 1) or the
  Kubernetes API directly (Phase 2). Bow MUST NOT reimplement
  resource application logic.
- Semver is enforced via the `semver` library. Version strings
  MUST be valid semver.

**Rationale:** PEP 20 — "Practicality beats purity." pip already
solves dependency resolution. kubectl already applies manifests.

### V. Flat is Better Than Nested

Keep abstractions shallow. Two levels of nesting (resource → leaf)
is the common case; three levels (Deployment → Container → Port)
is the maximum.

- Resource hierarchy follows the K8s object model, not arbitrary
  abstraction layers. No wrapper-of-wrapper patterns.
- Values are flat dicts merged via `deep_merge`. No custom value
  objects, no schema classes, no validation frameworks.
- Project structure is a single `src/bow/` package with four
  sub-packages (`core/`, `chart/`, `stack/`, `cli/`). New
  sub-packages MUST be justified against this constraint.

**Rationale:** PEP 20 — "Flat is better than nested." Every layer
of indirection is a layer of cognitive load.

### VI. Minimal Tests, Maximum Confidence

Test the public contract — rendered YAML output — not internal
implementation details. Every test MUST justify its existence.

- Tests target `render()` and `render_all()` output: the produced
  K8s manifest dict. If the YAML is correct, the internals are
  correct.
- Chart tests verify the full render pipeline: default values →
  value overrides → expected manifest structure.
- Stack tests verify parsing, merging, and reference resolution
  against known fixture files.
- No mocking of internal classes. No testing of private methods.
  No tests for getters/setters or trivial constructors.
- Coverage is measured by confidence in deployment correctness,
  not by line percentage.

**Rationale:** PEP 20 — "Readability counts" applies to tests
too. A test file MUST read as a specification of behavior, not
as an exercise in framework gymnastics.

## Technology & Constraints

- **Language:** Python ≥ 3.11
- **Build:** Hatchling (`pyproject.toml` driven)
- **Dependencies:** `pyyaml`, `click`, `semver` — no more without
  justification. Each new dependency MUST be reviewed.
- **Charts:** Each chart is a standalone pip package under
  `charts/bow-<name>/`. Chart version MUST follow semver.
  Default values MUST be in YAML format (`defaults.yaml`).
- **State:** Stateless. Kubernetes labels are the only tracking
  mechanism. No local database, no lock files for cluster state.
- **Stack format:** `bow.io/v1 Stack` API. Components reference
  each other via `${component_name.field}` syntax.

## Development Workflow

- Features are developed phase-by-phase as defined in AGENTS.md
  (core → cli → chart → stack → polish).
- Every change MUST keep the existing test suite green. New tests
  are added only when they test a new public contract or fix a
  regression.
- Commit messages follow conventional commits:
  `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- AGENTS.md is the single source of architectural truth.
  Constitution governs development principles and process.
- Use `AGENTS.md` for runtime development guidance and
  architectural reference.

## Governance

This constitution supersedes all ad-hoc practices. Every code
change and review MUST verify compliance with these principles.

- **Amendments** require: (1) a documented rationale,
  (2) version bump per semver, (3) updated Sync Impact Report.
- **Complexity** MUST be justified. Adding a new dependency, a
  new abstraction layer, or a new sub-package requires explicit
  rationale against Principles IV and V.
- **Exceptions** are permitted only when documented inline with
  a `# CONSTITUTION EXCEPTION: <rationale>` comment.

**Version**: 1.0.0 | **Ratified**: 2026-02-11 | **Last Amended**: 2026-02-11
