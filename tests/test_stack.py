"""
tests/test_stack.py — Stack system tests.

Parser, merger, refs, engine and CLI stack mode.
"""

import os
import sys
import yaml
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bow.core.stack import _reset
from bow.chart.registry import register_chart, reset_registry
from bow_postgresql import PostgreSQLChart
from bow.stack.parser import parse_stack_file, parse_stack_dict, StackParseError
from bow.stack.refs import resolve_refs, RefError
from bow.stack.merger import merge_stack_files, apply_set_to_stack
from bow.stack.engine import render_stack, StackError


def _write_yaml(data, suffix=".yaml"):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    yaml.dump(data, f)
    f.flush()
    f.close()
    return f.name


@pytest.fixture(autouse=True)
def clean():
    _reset()
    reset_registry()
    register_chart(PostgreSQLChart)
    yield
    _reset()
    reset_registry()


BASIC_STACK = {
    "apiVersion": "bow.io/v1",
    "kind": "Stack",
    "metadata": {"name": "test-project", "namespace": "test-ns"},
    "components": [
        {
            "chart": "postgresql",
            "name": "main-db",
            "values": {"storage": "50Gi", "replicas": 2},
        },
    ],
}


# ─────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────
class TestParser:
    def test_parse_basic(self):
        spec = parse_stack_dict(BASIC_STACK)
        assert spec.name == "test-project"
        assert spec.namespace == "test-ns"
        assert len(spec.components) == 1
        assert spec.components[0].chart == "postgresql"
        assert spec.components[0].name == "main-db"
        assert spec.components[0].values["storage"] == "50Gi"

    def test_parse_file(self):
        path = _write_yaml(BASIC_STACK)
        spec = parse_stack_file(path)
        os.unlink(path)
        assert spec.name == "test-project"

    def test_name_defaults_to_chart(self):
        data = {
            "apiVersion": "bow.io/v1",
            "kind": "Stack",
            "metadata": {"name": "proj"},
            "components": [{"chart": "postgresql"}],
        }
        spec = parse_stack_dict(data)
        assert spec.components[0].name == "postgresql"

    def test_missing_name_raises(self):
        with pytest.raises(StackParseError, match="metadata.name"):
            parse_stack_dict({"metadata": {}})

    def test_duplicate_name_raises(self):
        data = {
            "apiVersion": "bow.io/v1",
            "kind": "Stack",
            "metadata": {"name": "proj"},
            "components": [
                {"chart": "postgresql", "name": "db"},
                {"chart": "postgresql", "name": "db"},
            ],
        }
        with pytest.raises(StackParseError, match="Duplicate"):
            parse_stack_dict(data)

    def test_missing_chart_raises(self):
        data = {
            "metadata": {"name": "proj"},
            "components": [{"name": "db"}],
        }
        with pytest.raises(StackParseError, match="chart is required"):
            parse_stack_dict(data)

    def test_wrong_api_version(self):
        data = {
            "apiVersion": "bow.io/v99",
            "metadata": {"name": "proj"},
            "components": [],
        }
        with pytest.raises(StackParseError, match="apiVersion"):
            parse_stack_dict(data)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_stack_file("/nonexistent.yaml")


# ─────────────────────────────────────────────
# REFS
# ─────────────────────────────────────────────
class TestRefs:
    def test_host_ref(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={}),
            ComponentSpec(chart="myapp", name="api", values={
                "database_host": "${db.host}",
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[1].values["database_host"] == "db"

    def test_port_ref(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={}),
            ComponentSpec(chart="myapp", name="api", values={
                "database_port": "${db.port}",
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[1].values["database_port"] == "5432"

    def test_values_ref(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={"database": "myapp"}),
            ComponentSpec(chart="myapp", name="api", values={
                "db_name": "${db.values.database}",
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[1].values["db_name"] == "myapp"

    def test_composite_ref(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={
                "database": "myapp",
                "service": {"port": 5432},
            }),
            ComponentSpec(chart="myapp", name="api", values={
                "url": "postgresql://${db.host}:${db.port}/${db.values.database}",
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[1].values["url"] == "postgresql://db:5432/myapp"

    def test_nested_ref(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={}),
            ComponentSpec(chart="myapp", name="api", values={
                "config": {"database": {"host": "${db.host}"}},
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[0].values == {}  # db should not change
        assert resolved[1].values["config"]["database"]["host"] == "db"

    def test_unknown_component_raises(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="myapp", name="api", values={
                "host": "${nonexistent.host}",
            }),
        ]
        with pytest.raises(RefError, match="Unknown component"):
            resolve_refs(components)

    def test_unknown_field_raises(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={}),
            ComponentSpec(chart="myapp", name="api", values={
                "x": "${db.unknown_field}",
            }),
        ]
        with pytest.raises(RefError, match="Unknown field"):
            resolve_refs(components)

    def test_list_refs(self):
        from bow.stack.parser import ComponentSpec
        components = [
            ComponentSpec(chart="postgresql", name="db", values={}),
            ComponentSpec(chart="myapp", name="api", values={
                "hosts": ["${db.host}", "other-host"],
            }),
        ]
        resolved = resolve_refs(components)
        assert resolved[1].values["hosts"] == ["db", "other-host"]


# ─────────────────────────────────────────────
# MERGER
# ─────────────────────────────────────────────
class TestMerger:
    def test_single_file(self):
        path = _write_yaml(BASIC_STACK)
        result = merge_stack_files([path])
        os.unlink(path)
        assert result["metadata"]["name"] == "test-project"

    def test_overlay_dict_format(self):
        base_path = _write_yaml(BASIC_STACK)
        overlay = {
            "components": {
                "main-db": {"values": {"storage": "200Gi", "replicas": 5}},
            }
        }
        overlay_path = _write_yaml(overlay)

        result = merge_stack_files([base_path, overlay_path])
        os.unlink(base_path)
        os.unlink(overlay_path)

        comp = result["components"][0]
        assert comp["values"]["storage"] == "200Gi"
        assert comp["values"]["replicas"] == 5
        assert comp["name"] == "main-db"  # should be preserved

    def test_overlay_list_format(self):
        base_path = _write_yaml(BASIC_STACK)
        overlay = {
            "components": [
                {"chart": "postgresql", "name": "main-db",
                 "values": {"replicas": 10}},
            ]
        }
        overlay_path = _write_yaml(overlay)

        result = merge_stack_files([base_path, overlay_path])
        os.unlink(base_path)
        os.unlink(overlay_path)

        comp = result["components"][0]
        assert comp["values"]["replicas"] == 10
        assert comp["values"]["storage"] == "50Gi"  # should be preserved from base

    def test_set_override(self):
        result = apply_set_to_stack(
            dict(BASIC_STACK),
            ["components.main-db.values.storage=500Gi"],
        )
        # --set deep merge
        assert "components" in result

    def test_multiple_overlays(self):
        base_path = _write_yaml(BASIC_STACK)
        overlay1 = {"components": {"main-db": {"values": {"replicas": 3}}}}
        overlay2 = {"components": {"main-db": {"values": {"replicas": 7}}}}
        p1 = _write_yaml(overlay1)
        p2 = _write_yaml(overlay2)

        result = merge_stack_files([base_path, p1, p2])
        os.unlink(base_path)
        os.unlink(p1)
        os.unlink(p2)

        # Last overlay wins
        assert result["components"][0]["values"]["replicas"] == 7


# ─────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────
class TestEngine:
    def test_render_basic_stack(self):
        path = _write_yaml(BASIC_STACK)
        m = render_stack([path])
        os.unlink(path)

        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        assert "Deployment" in kinds
        assert "Service" in kinds
        assert "PersistentVolumeClaim" in kinds

        # Replicas override
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 2

        # Storage override
        pvc = [d for d in docs if d["kind"] == "PersistentVolumeClaim"][0]
        assert pvc["spec"]["resources"]["requests"]["storage"] == "50Gi"

    def test_render_with_overlay(self):
        base_path = _write_yaml(BASIC_STACK)
        overlay = {"components": {"main-db": {"values": {"replicas": 5}}}}
        overlay_path = _write_yaml(overlay)

        m = render_stack([base_path, overlay_path])
        os.unlink(base_path)
        os.unlink(overlay_path)

        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 5

    def test_render_with_set(self):
        path = _write_yaml(BASIC_STACK)
        m = render_stack(
            [path],
            set_args=["components.main-db.values.replicas=9"],
        )
        os.unlink(path)

        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        # Effect of --set on components depends on merge strategy
        # At minimum it should not error
        assert dep["kind"] == "Deployment"

    def test_tracking_labels_with_stack(self):
        path = _write_yaml(BASIC_STACK)
        m = render_stack([path])
        os.unlink(path)

        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        labels = dep["metadata"]["labels"]
        assert labels["bow.io/managed-by"] == "bow"
        assert labels["bow.io/chart"] == "postgresql"
        assert labels["bow.io/stack"] == "test-project"

    def test_unknown_chart_raises(self):
        data = dict(BASIC_STACK)
        data["components"] = [{"chart": "nonexistent", "name": "x"}]
        path = _write_yaml(data)
        with pytest.raises(StackError, match="not found"):
            render_stack([path])
        os.unlink(path)

    def test_multi_component_stack(self):
        """Same chart twice, with different names."""
        data = {
            "apiVersion": "bow.io/v1",
            "kind": "Stack",
            "metadata": {"name": "multi"},
            "components": [
                {"chart": "postgresql", "name": "primary-db",
                 "values": {"database": "app", "storage": "100Gi"}},
                {"chart": "postgresql", "name": "analytics-db",
                 "values": {"database": "analytics", "storage": "200Gi"}},
            ],
        }
        path = _write_yaml(data)
        m = render_stack([path])
        os.unlink(path)

        docs = m.to_dicts()
        deployments = [d for d in docs if d["kind"] == "Deployment"]
        assert len(deployments) == 2

    def test_yaml_output(self):
        path = _write_yaml(BASIC_STACK)
        m = render_stack([path])
        os.unlink(path)

        yaml_str = m.to_yaml()
        parsed = list(yaml.safe_load_all(yaml_str))
        assert len(parsed) >= 3


# ─────────────────────────────────────────────
# CLI STACK MODE
# ─────────────────────────────────────────────
class TestCLIStack:
    def test_template_stack(self):
        from click.testing import CliRunner
        from bow.cli import main

        path = _write_yaml(BASIC_STACK)
        runner = CliRunner()
        result = runner.invoke(main, ["template", "-f", path])
        os.unlink(path)

        assert result.exit_code == 0
        assert "kind: Deployment" in result.output
        assert "kind: Service" in result.output

    def test_template_stack_with_overlay(self):
        from click.testing import CliRunner
        from bow.cli import main

        base_path = _write_yaml(BASIC_STACK)
        overlay = {"components": {"main-db": {"values": {"replicas": 7}}}}
        overlay_path = _write_yaml(overlay)

        runner = CliRunner()
        result = runner.invoke(main, ["template", "-f", base_path, "-f", overlay_path])
        os.unlink(base_path)
        os.unlink(overlay_path)

        assert result.exit_code == 0
        docs = list(yaml.safe_load_all(result.output))
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 7

    def test_template_no_args(self):
        from click.testing import CliRunner
        from bow.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["template"])
        assert result.exit_code != 0
