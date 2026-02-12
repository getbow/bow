"""
bow.oci.client — OCI registry client.

Pushes/pulls charts as OCI artifacts.
Simple HTTP-based OCI Distribution Spec client.

OCI artifact structure:
  manifest.json
    ├── config: application/vnd.bow.chart.config.v1+json
    └── layer[0]: application/vnd.bow.chart.content.v1.tar+gzip

First version: filesystem-based mock.
OCI HTTP client to be added later (oras-py or custom).
Currently charts are copied directly as tar.gz into the
registry directory — for local development and testing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


CHART_CONFIG_MEDIA_TYPE = "application/vnd.bow.chart.config.v1+json"
CHART_CONTENT_MEDIA_TYPE = "application/vnd.bow.chart.content.v1.tar+gzip"


@dataclass
class ChartArtifact:
    """A chart packaged as an OCI artifact."""
    name: str
    version: str
    description: str = ""
    digest: str = ""         # sha256:...
    registry: str = ""       # oci://...
    tar_path: Path | None = None
    config: dict[str, Any] | None = None


class OCIError(Exception):
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHART PACKING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def pack_chart(chart_dir: str | Path) -> ChartArtifact:
    """Package a chart directory as an OCI artifact.

    chart_dir structure (bow-postgresql/):
        ├── pyproject.toml
        └── src/bow_postgresql/
            ├── __init__.py
            └── defaults.yaml

    Or simple structure:
        ├── chart.json
        ├── __init__.py
        └── defaults.yaml

    Returns:
        ChartArtifact (tar_path is set)
    """
    chart_dir = Path(chart_dir)

    # Find chart metadata
    config = _read_chart_config(chart_dir)
    name = config["name"]
    version = config["version"]

    # Create tar.gz
    tar_path = Path(tempfile.mkdtemp()) / f"{name}-{version}.tar.gz"

    with tarfile.open(tar_path, "w:gz") as tar:
        # chart.json (metadata)
        config_bytes = json.dumps(config, indent=2).encode()
        config_info = tarfile.TarInfo(name="chart.json")
        config_info.size = len(config_bytes)
        tar.addfile(config_info, BytesIO(config_bytes))

        # Chart source files
        src_dir = _find_chart_src(chart_dir, name)
        if src_dir and src_dir.exists():
            for fp in sorted(src_dir.rglob("*")):
                if fp.is_file() and not fp.name.startswith(".") \
                   and "__pycache__" not in str(fp):
                    arcname = str(fp.relative_to(src_dir.parent))
                    tar.add(str(fp), arcname=arcname)

        # pyproject.toml (needed for pip install)
        pyproject = chart_dir / "pyproject.toml"
        if pyproject.exists():
            tar.add(str(pyproject), arcname="pyproject.toml")

        # Preserve src directory structure
        src_root = chart_dir / "src"
        if src_root.exists():
            # Include files like src/__init__.py
            for fp in sorted(src_root.rglob("*")):
                if fp.is_file() and not fp.name.startswith(".") \
                   and "__pycache__" not in str(fp):
                    arcname = str(fp.relative_to(chart_dir))
                    tar.add(str(fp), arcname=arcname)

    # Compute digest
    digest = _compute_file_digest(tar_path)

    return ChartArtifact(
        name=name,
        version=version,
        description=config.get("description", ""),
        digest=digest,
        tar_path=tar_path,
        config=config,
    )


def unpack_chart(tar_path: str | Path, dest_dir: str | Path) -> Path:
    """Extract a chart tar.gz into a directory.

    Returns:
        The extracted directory
    """
    tar_path = Path(tar_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(dest_dir, filter="data")

    return dest_dir


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL REGISTRY (filesystem-based mock)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def push_chart(
    artifact: ChartArtifact,
    registry_url: str,
) -> str:
    """Push a chart to a registry.

    Currently a local filesystem registry:
      oci://local → ~/.bow/registry/
      oci:///path/to/registry → custom path

    Returns:
        Full reference (oci://registry/name:version)
    """
    registry_path = _resolve_registry_path(registry_url)
    registry_path.mkdir(parents=True, exist_ok=True)

    chart_path = registry_path / artifact.name
    chart_path.mkdir(parents=True, exist_ok=True)

    # Tag directory
    tag_path = chart_path / artifact.version
    tag_path.mkdir(parents=True, exist_ok=True)

    # Copy artifact
    if artifact.tar_path:
        dest = tag_path / f"{artifact.name}-{artifact.version}.tar.gz"
        shutil.copy2(artifact.tar_path, dest)

    # Write manifest
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": CHART_CONFIG_MEDIA_TYPE,
            "digest": artifact.digest,
            "data": artifact.config,
        },
        "layers": [
            {
                "mediaType": CHART_CONTENT_MEDIA_TYPE,
                "digest": artifact.digest,
                "size": artifact.tar_path.stat().st_size if artifact.tar_path else 0,
            }
        ],
    }
    with open(tag_path / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    ref = f"{registry_url.rstrip('/')}/{artifact.name}:{artifact.version}"
    return ref


def pull_chart(
    name: str,
    version: str,
    registry_url: str,
    cache_dir: str | Path,
) -> ChartArtifact:
    """Pull a chart from a registry.

    Returns:
        ChartArtifact (tar_path points to the cached file)
    """
    registry_path = _resolve_registry_path(registry_url)
    tag_path = registry_path / name / version
    cache_dir = Path(cache_dir)

    if not tag_path.exists():
        raise OCIError(
            f"Chart not found: {name}:{version} in {registry_url}"
        )

    # Read manifest
    manifest_file = tag_path / "manifest.json"
    if not manifest_file.exists():
        raise OCIError(f"Manifest not found for {name}:{version}")

    with open(manifest_file) as f:
        manifest = json.load(f)

    config = manifest.get("config", {}).get("data", {})
    digest = manifest.get("config", {}).get("digest", "")

    # Find tar.gz
    tar_files = list(tag_path.glob("*.tar.gz"))
    if not tar_files:
        raise OCIError(f"No artifact found for {name}:{version}")

    # Copy to cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_tar = cache_dir / tar_files[0].name
    if not cache_tar.exists():
        shutil.copy2(tar_files[0], cache_tar)

    return ChartArtifact(
        name=name,
        version=version,
        description=config.get("description", ""),
        digest=digest,
        registry=registry_url,
        tar_path=cache_tar,
        config=config,
    )


def list_remote_charts(registry_url: str) -> list[dict[str, str]]:
    """List charts in a registry."""
    registry_path = _resolve_registry_path(registry_url)
    if not registry_path.exists():
        return []

    charts = []
    for chart_dir in sorted(registry_path.iterdir()):
        if chart_dir.is_dir():
            for version_dir in sorted(chart_dir.iterdir()):
                if version_dir.is_dir():
                    charts.append({
                        "name": chart_dir.name,
                        "version": version_dir.name,
                    })
    return charts


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _read_chart_config(chart_dir: Path) -> dict[str, Any]:
    """Read metadata from a chart directory."""
    # 1. chart.json (new format)
    chart_json = chart_dir / "chart.json"
    if chart_json.exists():
        with open(chart_json) as f:
            return json.load(f)

    # 2. Parse from pyproject.toml
    pyproject = chart_dir / "pyproject.toml"
    if pyproject.exists():
        return _parse_pyproject_config(pyproject)

    raise OCIError(f"No chart.json or pyproject.toml found in {chart_dir}")


def _parse_pyproject_config(pyproject: Path) -> dict[str, Any]:
    """Read chart config from pyproject.toml."""
    # Simple TOML parser (only the parts we need)
    import tomllib
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    name = project.get("name", "")
    # bow-postgresql → postgresql
    chart_name = name.replace("bow-", "")

    # Find chart class from entry_points
    eps = project.get("entry-points", {}).get("bow.charts", {})

    return {
        "name": chart_name,
        "version": project.get("version", "0.0.0"),
        "description": project.get("description", ""),
        "package_name": name,
        "entry_points": eps,
    }


def _find_chart_src(chart_dir: Path, chart_name: str) -> Path | None:
    """Find the chart source directory."""
    # bow-postgresql → bow_postgresql
    pkg_name = f"bow_{chart_name}"
    src = chart_dir / "src" / pkg_name
    if src.exists():
        return src
    # Directly under chart_dir
    init = chart_dir / "__init__.py"
    if init.exists():
        return chart_dir
    return None


def _compute_file_digest(path: Path) -> str:
    """Compute the SHA256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _resolve_registry_path(url: str) -> Path:
    """Convert a registry URL to a filesystem path.

    oci://local → ~/.bow/registry/local
    oci:///absolute/path → /absolute/path
    file:///path → /path
    """
    from bow.oci.config import BOW_HOME

    url = url.strip()
    if url.startswith("oci://"):
        remainder = url[6:]
        if remainder.startswith("/"):
            return Path(remainder)
        return BOW_HOME / "registry" / remainder
    if url.startswith("file://"):
        return Path(url[7:])
    return BOW_HOME / "registry" / url
