"""
tests/test_chart.py — Chart system tests.

Values merge, chart render, registry, dependency.
"""

import os
import sys
import yaml
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bow.core.stack import _reset
from bow.chart.values import deep_merge, parse_set_values, merge_all_values
from bow.chart.registry import register_chart, get_chart, list_charts, reset_registry
from bow.chart.dependency import ChartDep, resolve_condition, get_dep_values
from bow_postgresql import PostgreSQLChart


@pytest.fixture(autouse=True)
def clean():
    _reset()
    reset_registry()
    register_chart(PostgreSQLChart)
    yield
    _reset()
    reset_registry()


# ─────────────────────────────────────────────
# VALUES MERGE
# ─────────────────────────────────────────────
class TestDeepMerge:
    def test_simple_merge(self):
        result = deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"host": "prod-db"}}
        result = deep_merge(base, override)
        assert result == {"db": {"host": "prod-db", "port": 5432}}

    def test_deep_nested(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": {"c": 99, "d": 2}}}

    def test_override_dict_with_scalar(self):
        """Scalar override completely replaces dict."""
        base = {"db": {"host": "localhost"}}
        override = {"db": "external"}
        result = deep_merge(base, override)
        assert result == {"db": "external"}

    def test_does_not_mutate(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}  # should not be mutated


class TestParseSetValues:
    def test_simple(self):
        result = parse_set_values(["replicas=3"])
        assert result == {"replicas": 3}

    def test_nested(self):
        result = parse_set_values(["postgresql.storage=50Gi"])
        assert result == {"postgresql": {"storage": "50Gi"}}

    def test_bool(self):
        result = parse_set_values(["metrics.enabled=true"])
        assert result == {"metrics": {"enabled": True}}

    def test_false(self):
        result = parse_set_values(["postgresql.enabled=false"])
        assert result == {"postgresql": {"enabled": False}}

    def test_multiple(self):
        result = parse_set_values(["replicas=3", "storage=50Gi", "metrics.enabled=true"])
        assert result == {"replicas": 3, "storage": "50Gi", "metrics": {"enabled": True}}

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_set_values(["invalid"])


class TestMergeAllValues:
    def test_with_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"replicas": 5, "storage": "100Gi"}, f)
            f.flush()
            result = merge_all_values(
                {"replicas": 1, "storage": "10Gi", "database": "appdb"},
                [f.name],
                [],
            )
        os.unlink(f.name)
        assert result["replicas"] == 5
        assert result["storage"] == "100Gi"
        assert result["database"] == "appdb"  # default preserved

    def test_set_overrides_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"replicas": 5}, f)
            f.flush()
            result = merge_all_values(
                {"replicas": 1},
                [f.name],
                ["replicas=10"],
            )
        os.unlink(f.name)
        assert result["replicas"] == 10  # --set wins

    def test_multiple_files(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f1:
            yaml.dump({"replicas": 3, "storage": "50Gi"}, f1)
            f1.flush()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f2:
            yaml.dump({"replicas": 5}, f2)
            f2.flush()
            result = merge_all_values({}, [f1.name, f2.name], [])
        os.unlink(f1.name)
        os.unlink(f2.name)
        assert result["replicas"] == 5    # second file wins
        assert result["storage"] == "50Gi"  # preserved from first file

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            merge_all_values({}, ["/nonexistent.yaml"], [])


# ─────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────
class TestRegistry:
    def test_register_and_get(self):
        chart = get_chart("postgresql")
        assert chart is not None
        assert chart.name == "postgresql"
        assert chart.version == "16.4.0"

    def test_get_missing(self):
        chart = get_chart("nonexistent")
        assert chart is None

    def test_list_charts(self):
        charts = list_charts()
        assert "postgresql" in charts


# ─────────────────────────────────────────────
# DEPENDENCY
# ─────────────────────────────────────────────
class TestDependency:
    def test_resolve_condition_true(self):
        assert resolve_condition({"pg": {"enabled": True}}, "pg.enabled") is True

    def test_resolve_condition_false(self):
        assert resolve_condition({"pg": {"enabled": False}}, "pg.enabled") is False

    def test_resolve_condition_missing(self):
        """Default True when key is missing."""
        assert resolve_condition({}, "pg.enabled") is True

    def test_resolve_condition_none(self):
        assert resolve_condition({}, None) is True

    def test_get_dep_values(self):
        dep = ChartDep("postgresql", default_values={"storage": "10Gi"})
        values = {"postgresql": {"storage": "50Gi", "replicas": 3}}
        result = get_dep_values(values, dep)
        assert result["storage"] == "50Gi"
        assert result["replicas"] == 3


# ─────────────────────────────────────────────
# CHART TEMPLATE
# ─────────────────────────────────────────────
class TestChartTemplate:
    def test_postgresql_default(self):
        chart = get_chart("postgresql")
        m = chart.template()
        docs = m.to_dicts()
        kinds = [d["kind"] for d in docs]
        assert "PersistentVolumeClaim" in kinds
        assert "Deployment" in kinds
        assert "Service" in kinds

    def test_postgresql_override_replicas(self):
        chart = get_chart("postgresql")
        m = chart.template(set_args=["replicas=3"])
        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 3

    def test_postgresql_override_storage(self):
        chart = get_chart("postgresql")
        m = chart.template(set_args=["storage=100Gi"])
        pvc = [d for d in m.to_dicts() if d["kind"] == "PersistentVolumeClaim"][0]
        assert pvc["spec"]["resources"]["requests"]["storage"] == "100Gi"

    def test_postgresql_with_values_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "replicas": 2,
                "storage": "50Gi",
                "database": "mydb",
                "metrics": {"enabled": True},
            }, f)
            f.flush()
            chart = get_chart("postgresql")
            m = chart.template(value_files=[f.name])
        os.unlink(f.name)

        docs = m.to_dicts()
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 2

        # Metrics sidecar container eklenmeli
        containers = dep["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 2
        assert containers[1]["name"] == "exporter"

    def test_postgresql_yaml_output(self):
        chart = get_chart("postgresql")
        m = chart.template()
        yaml_str = m.to_yaml()
        # Valid multi-document YAML
        docs = list(yaml.safe_load_all(yaml_str))
        assert len(docs) >= 3

    def test_postgresql_tracking_labels(self):
        chart = get_chart("postgresql")
        m = chart.template()
        dep = [d for d in m.to_dicts() if d["kind"] == "Deployment"][0]
        labels = dep["metadata"]["labels"]
        assert labels["bow.io/managed-by"] == "bow"
        assert labels["bow.io/chart"] == "postgresql"
        assert labels["bow.io/version"] == "16.4.0"
