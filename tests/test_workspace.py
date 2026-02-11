"""
tests/test_workspace.py — Workspace tests.

Lock parse/write, stage resolver, checksum/drift,
workspace resolver, CLI workspace mode.
"""

import os
import sys
import yaml
import pytest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bow.core.stack import _reset
from bow.chart.registry import register_chart, reset_registry
from bow_postgresql import PostgreSQLChart
from bow_redis import RedisChart
from bow_redmine import RedmineChart
from bow.workspace.lock import (
    LockSpec, parse_lock, write_lock, compute_checksum, check_drift, LockError,
)
from bow.workspace.stage import resolve_stages, resolve_value_files
from bow.workspace.resolver import resolve_workspace, WorkspaceError


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


def _make_workspace(files: dict[str, str | dict]) -> str:
    """Create a temporary workspace directory."""
    tmpdir = tempfile.mkdtemp()
    for name, content in files.items():
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            if isinstance(content, dict):
                yaml.dump(content, f)
            else:
                f.write(content)
    return tmpdir


# ─────────────────────────────────────────────
# LOCK
# ─────────────────────────────────────────────
class TestLock:
    def test_parse_chart_lock(self):
        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nversion: '16.4.0'\nnamespace: t1\n",
        })
        lock = parse_lock(os.path.join(ws, "bow.lock"))
        assert lock.chart == "postgresql"
        assert lock.version == "16.4.0"
        assert lock.namespace == "t1"
        assert not lock.is_stack
        shutil.rmtree(ws)

    def test_parse_stack_lock(self):
        ws = _make_workspace({
            "bow.lock": "stack: stack.yaml\nnamespace: t3\n",
        })
        lock = parse_lock(os.path.join(ws, "bow.lock"))
        assert lock.stack == "stack.yaml"
        assert lock.is_stack
        shutil.rmtree(ws)

    def test_parse_missing_raises(self):
        with pytest.raises(LockError, match="not found"):
            parse_lock("/nonexistent/bow.lock")

    def test_parse_no_chart_no_stack_raises(self):
        ws = _make_workspace({
            "bow.lock": "namespace: t1\n",
        })
        with pytest.raises(LockError, match="either"):
            parse_lock(os.path.join(ws, "bow.lock"))
        shutil.rmtree(ws)

    def test_parse_both_raises(self):
        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nstack: stack.yaml\n",
        })
        with pytest.raises(LockError, match="both"):
            parse_lock(os.path.join(ws, "bow.lock"))
        shutil.rmtree(ws)

    def test_write_and_read(self):
        ws = _make_workspace({})
        lock_path = os.path.join(ws, "bow.lock")
        lock = LockSpec(
            chart="postgresql", version="16.4.0",
            namespace="t1", checksum="sha256:abc123",
        )
        write_lock(lock, lock_path)
        parsed = parse_lock(lock_path)
        assert parsed.chart == "postgresql"
        assert parsed.version == "16.4.0"
        assert parsed.checksum == "sha256:abc123"
        shutil.rmtree(ws)

    def test_display_name(self):
        assert LockSpec(chart="pg", version="1.0").display_name == "pg@1.0"
        assert LockSpec(chart="pg").display_name == "pg"
        assert LockSpec(stack="stack.yaml").display_name == "stack.yaml"


# ─────────────────────────────────────────────
# CHECKSUM & DRIFT
# ─────────────────────────────────────────────
class TestChecksum:
    def test_checksum_deterministic(self):
        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        c1 = compute_checksum(ws)
        c2 = compute_checksum(ws)
        assert c1 == c2
        assert c1.startswith("sha256:")
        shutil.rmtree(ws)

    def test_checksum_changes_on_content(self):
        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        c1 = compute_checksum(ws)
        with open(os.path.join(ws, "values.yaml"), "w") as f:
            f.write("replicas: 5\n")
        c2 = compute_checksum(ws)
        assert c1 != c2
        shutil.rmtree(ws)

    def test_checksum_includes_stage_files(self):
        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        c1 = compute_checksum(ws)
        with open(os.path.join(ws, "values.prod.yaml"), "w") as f:
            f.write("replicas: 5\n")
        c2 = compute_checksum(ws)
        assert c1 != c2
        shutil.rmtree(ws)

    def test_drift_detected(self):
        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        checksum = compute_checksum(ws)
        lock = LockSpec(chart="pg", checksum=checksum)
        assert not check_drift(ws, lock)

        # Modify
        with open(os.path.join(ws, "values.yaml"), "w") as f:
            f.write("replicas: 99\n")
        assert check_drift(ws, lock)
        shutil.rmtree(ws)

    def test_no_drift_without_checksum(self):
        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        lock = LockSpec(chart="pg")  # no checksum
        assert not check_drift(ws, lock)
        shutil.rmtree(ws)


# ─────────────────────────────────────────────
# STAGE
# ─────────────────────────────────────────────
class TestStage:
    def test_flag_priority(self):
        os.environ["KUBRIC_STAGE"] = "staging"
        assert resolve_stages(["prod"]) == ["prod"]
        del os.environ["KUBRIC_STAGE"]

    def test_env_fallback(self):
        os.environ["KUBRIC_STAGE"] = "prod"
        assert resolve_stages() == ["prod"]
        del os.environ["KUBRIC_STAGE"]

    def test_env_comma(self):
        os.environ["KUBRIC_STAGE"] = "prod,eu-west"
        assert resolve_stages() == ["prod", "eu-west"]
        del os.environ["KUBRIC_STAGE"]

    def test_no_stage(self):
        assert resolve_stages() == []

    def test_resolve_value_files(self):
        ws = _make_workspace({
            "values.yaml": "a: 1\n",
            "values.prod.yaml": "b: 2\n",
            "values.staging.yaml": "c: 3\n",
        })
        files = resolve_value_files(ws, ["prod"])
        assert len(files) == 2
        assert files[0].endswith("values.yaml")
        assert files[1].endswith("values.prod.yaml")
        shutil.rmtree(ws)

    def test_resolve_multiple_stages(self):
        ws = _make_workspace({
            "values.yaml": "a: 1\n",
            "values.prod.yaml": "b: 2\n",
            "values.eu.yaml": "c: 3\n",
        })
        files = resolve_value_files(ws, ["prod", "eu"])
        assert len(files) == 3
        shutil.rmtree(ws)


# ─────────────────────────────────────────────
# WORKSPACE RESOLVER
# ─────────────────────────────────────────────
class TestResolver:
    def test_chart_workspace(self):
        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nversion: '16.4.0'\nnamespace: t1\n",
            "values.yaml": "replicas: 2\nstorage: 50Gi\n",
        })
        plan = resolve_workspace(ws)
        assert plan.lock.chart == "postgresql"
        assert plan.namespace == "t1"
        assert not plan.is_stack
        assert len(plan.files) == 1
        shutil.rmtree(ws)

    def test_chart_workspace_with_stage(self):
        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nversion: '16.4.0'\nnamespace: t1\n",
            "values.yaml": "replicas: 1\n",
            "values.prod.yaml": "replicas: 5\n",
        })
        plan = resolve_workspace(ws, stage_flags=["prod"])
        assert plan.stages == ["prod"]
        assert len(plan.files) == 2
        shutil.rmtree(ws)

    def test_stack_workspace(self):
        ws = _make_workspace({
            "bow.lock": "stack: stack.yaml\nnamespace: t3\n",
            "stack.yaml": yaml.dump({
                "apiVersion": "bow.io/v1",
                "kind": "Stack",
                "metadata": {"name": "test", "namespace": "t3"},
                "components": [{"chart": "postgresql", "name": "db"}],
            }),
        })
        plan = resolve_workspace(ws)
        assert plan.is_stack
        assert any("stack.yaml" in f for f in plan.files)
        shutil.rmtree(ws)

    def test_no_lock_raises(self):
        ws = _make_workspace({"values.yaml": "a: 1\n"})
        with pytest.raises(WorkspaceError, match="not found"):
            resolve_workspace(ws)
        shutil.rmtree(ws)

    def test_drift_flag(self):
        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nchecksum: sha256:old\n",
            "values.yaml": "replicas: 1\n",
        })
        plan = resolve_workspace(ws)
        assert plan.has_drift  # checksum mismatch
        shutil.rmtree(ws)


# ─────────────────────────────────────────────
# CLI WORKSPACE MODE
# ─────────────────────────────────────────────
class TestCLIWorkspace:
    def test_template_workspace(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nversion: '16.4.0'\nnamespace: t1\n",
            "values.yaml": "replicas: 2\nstorage: 50Gi\n",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["template", "-C", ws])
        assert result.exit_code == 0
        assert "kind: Deployment" in result.output

        docs = list(yaml.safe_load_all(result.output))
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 2
        shutil.rmtree(ws)

    def test_template_workspace_with_stage(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nnamespace: t1\n",
            "values.yaml": "replicas: 1\nstorage: 10Gi\n",
            "values.prod.yaml": "replicas: 5\nstorage: 200Gi\n",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["template", "-C", ws, "--stage", "prod"])
        assert result.exit_code == 0

        docs = list(yaml.safe_load_all(result.output))
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 5
        shutil.rmtree(ws)

    def test_template_workspace_stack(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "bow.lock": "stack: stack.yaml\nnamespace: t3\n",
            "stack.yaml": yaml.dump({
                "apiVersion": "bow.io/v1",
                "kind": "Stack",
                "metadata": {"name": "test", "namespace": "t3"},
                "components": [
                    {"chart": "postgresql", "name": "db",
                     "values": {"storage": "50Gi"}},
                ],
            }),
        })

        runner = CliRunner()
        result = runner.invoke(main, ["template", "-C", ws])
        assert result.exit_code == 0
        assert "kind: Deployment" in result.output
        shutil.rmtree(ws)

    def test_status_clean(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })
        checksum = compute_checksum(ws)
        with open(os.path.join(ws, "bow.lock"), "w") as f:
            yaml.dump({
                "chart": "postgresql",
                "version": "16.4.0",
                "namespace": "t1",
                "checksum": checksum,
            }, f)

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-C", ws])
        assert result.exit_code == 0
        assert "No drift" in result.output
        shutil.rmtree(ws)

    def test_status_drift(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "bow.lock": "chart: postgresql\nchecksum: sha256:stale\n",
            "values.yaml": "replicas: 1\n",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-C", ws])
        assert result.exit_code == 0
        assert "DRIFT" in result.output
        shutil.rmtree(ws)

    def test_lock_init_and_update(self):
        from click.testing import CliRunner
        from bow.cli import main

        ws = _make_workspace({
            "values.yaml": "replicas: 1\n",
        })

        runner = CliRunner()
        # Init
        result = runner.invoke(main, [
            "lock", "--init", "postgresql", "-n", "t1", "-C", ws,
        ])
        assert result.exit_code == 0

        # Lock file should have been created
        lock = parse_lock(os.path.join(ws, "bow.lock"))
        assert lock.chart == "postgresql"
        assert lock.namespace == "t1"
        assert lock.checksum is not None

        # Modify
        with open(os.path.join(ws, "values.yaml"), "w") as f:
            f.write("replicas: 99\n")

        # Update
        result = runner.invoke(main, ["lock", "-C", ws])
        assert result.exit_code == 0
        assert "updated" in result.output

        shutil.rmtree(ws)
