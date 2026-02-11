"""
tests/test_cli.py — CLI tests.

Tests commands using Click CliRunner.
"""

import os
import sys
import yaml
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from click.testing import CliRunner

from bow.core.stack import _reset
from bow.chart.registry import register_chart, reset_registry
from bow_postgresql import PostgreSQLChart
from bow.cli import main


@pytest.fixture(autouse=True)
def clean():
    _reset()
    reset_registry()
    register_chart(PostgreSQLChart)
    yield
    _reset()
    reset_registry()


runner = CliRunner()


class TestTemplate:
    def test_template_default(self):
        result = runner.invoke(main, ["template", "postgresql"])
        assert result.exit_code == 0
        assert "kind: Deployment" in result.output
        assert "kind: Service" in result.output

    def test_template_with_set(self):
        result = runner.invoke(main, [
            "template", "postgresql",
            "--set", "replicas=5",
            "--set", "storage=100Gi",
        ])
        assert result.exit_code == 0
        docs = list(yaml.safe_load_all(result.output))
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 5

    def test_template_with_values_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"replicas": 7, "database": "testdb"}, f)
            f.flush()
            result = runner.invoke(main, [
                "template", "postgresql",
                "-f", f.name,
            ])
        os.unlink(f.name)
        assert result.exit_code == 0
        docs = list(yaml.safe_load_all(result.output))
        dep = [d for d in docs if d["kind"] == "Deployment"][0]
        assert dep["spec"]["replicas"] == 7

    def test_template_chart_not_found(self):
        result = runner.invoke(main, ["template", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output or "not found" in (result.output + str(result.exception or ""))

    def test_template_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            outpath = f.name
        result = runner.invoke(main, [
            "template", "postgresql",
            "-o", outpath,
        ])
        assert result.exit_code == 0
        with open(outpath) as f:
            content = f.read()
        os.unlink(outpath)
        assert "kind: Deployment" in content


class TestList:
    def test_list_charts(self):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "postgresql" in result.output


class TestInspect:
    def test_inspect_chart(self):
        result = runner.invoke(main, ["inspect", "postgresql"])
        assert result.exit_code == 0
        assert "postgresql" in result.output
        assert "16.4.0" in result.output

    def test_inspect_not_found(self):
        result = runner.invoke(main, ["inspect", "nonexistent"])
        assert result.exit_code != 0
