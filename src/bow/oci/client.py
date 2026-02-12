"""
bow.oci.client — OCI registry client.

Pushes/pulls charts as OCI artifacts.

Supports two backends:
  1. Local filesystem registry (oci://local) — for development/testing
  2. Remote OCI registries (ghcr.io, harbor, etc.) — via oras-py SDK

OCI artifact structure:
  manifest.json
    ├── config: application/vnd.bow.chart.config.v1+json
    └── layer[0]: application/vnd.bow.chart.content.v1.tar+gzip
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


CHART_CONFIG_MEDIA_TYPE = "application/vnd.bow.chart.config.v1+json"
CHART_CONTENT_MEDIA_TYPE = "application/vnd.bow.chart.content.v1.tar+gzip"


def _is_remote_registry(url: str) -> bool:
    """Check if a registry URL points to a remote OCI registry.

    Remote registries are anything that is NOT:
      - oci://local
      - oci:///absolute/path (filesystem)
      - file:///path

    Examples of remote:
      - oci://ghcr.io/getbow/charts
      - oci://harbor.internal/bow
      - ghcr.io/getbow/charts
    """
    url = url.strip()
    if url.startswith("file://"):
        return False
    if url.startswith("oci://"):
        remainder = url[6:]
        # oci://local → local filesystem
        if remainder == "local" or remainder.startswith("local/"):
            return False
        # oci:///absolute/path → local filesystem
        if remainder.startswith("/"):
            return False
        # oci://ghcr.io/... → remote
        return True
    # Bare hostname like ghcr.io/getbow/charts
    if "." in url.split("/")[0]:
        return True
    return False


def _registry_to_oras_target(registry_url: str, name: str, version: str) -> str:
    """Convert bow registry URL + chart name/version to an oras target string.

    oci://ghcr.io/getbow/charts + valkey + 0.1.0
      → ghcr.io/getbow/charts/valkey:0.1.0
    """
    url = registry_url.strip().rstrip("/")
    if url.startswith("oci://"):
        url = url[6:]
    return f"{url}/{name}:{version}"


def _get_oras_client():
    """Create an oras client with Docker credential support.

    Handles macOS Keychain (osxkeychain), Linux secretservice,
    and plain Docker config.json credentials.
    """
    import oras.client
    import oras.provider

    client = oras.client.OrasClient()

    # oras-py doesn't always pick up credsStore helpers automatically.
    # Try to load credentials from the Docker credential helper.
    try:
        _load_docker_creds_into_oras(client)
    except Exception:
        pass  # Best effort — user can always do `bow registry login`

    return client


def _load_docker_creds_into_oras(client):
    """Load Docker credsStore credentials into oras client.

    Docker Desktop stores credentials via helpers like
    docker-credential-osxkeychain (macOS) or
    docker-credential-secretservice (Linux).
    """
    import json
    import subprocess
    from pathlib import Path

    docker_config = Path.home() / ".docker" / "config.json"
    if not docker_config.exists():
        return

    with open(docker_config) as f:
        config = json.load(f)

    creds_store = config.get("credsStore")
    if not creds_store:
        return  # Credentials are inline — oras handles this fine

    helper = f"docker-credential-{creds_store}"

    # For each registry in auths, get credentials from the helper
    for registry in config.get("auths", {}):
        try:
            result = subprocess.run(
                [helper, "get"],
                input=registry,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                creds = json.loads(result.stdout)
                username = creds.get("Username", "")
                secret = creds.get("Secret", "")
                if username and secret:
                    client.login(
                        hostname=registry,
                        username=username,
                        password=secret,
                    )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            continue


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
def _push_chart_local(
    artifact: ChartArtifact,
    registry_url: str,
) -> str:
    """Push a chart to a local filesystem registry."""
    registry_path = _resolve_registry_path(registry_url)
    registry_path.mkdir(parents=True, exist_ok=True)

    chart_path = registry_path / artifact.name
    chart_path.mkdir(parents=True, exist_ok=True)

    tag_path = chart_path / artifact.version
    tag_path.mkdir(parents=True, exist_ok=True)

    if artifact.tar_path:
        dest = tag_path / f"{artifact.name}-{artifact.version}.tar.gz"
        shutil.copy2(artifact.tar_path, dest)

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


def _pull_chart_local(
    name: str,
    version: str,
    registry_url: str,
    cache_dir: str | Path,
) -> ChartArtifact:
    """Pull a chart from a local filesystem registry."""
    registry_path = _resolve_registry_path(registry_url)
    tag_path = registry_path / name / version
    cache_dir = Path(cache_dir)

    if not tag_path.exists():
        raise OCIError(
            f"Chart not found: {name}:{version} in {registry_url}"
        )

    manifest_file = tag_path / "manifest.json"
    if not manifest_file.exists():
        raise OCIError(f"Manifest not found for {name}:{version}")

    with open(manifest_file) as f:
        manifest = json.load(f)

    config = manifest.get("config", {}).get("data", {})
    digest = manifest.get("config", {}).get("digest", "")

    tar_files = list(tag_path.glob("*.tar.gz"))
    if not tar_files:
        raise OCIError(f"No artifact found for {name}:{version}")

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REMOTE REGISTRY (oras-py based)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _push_chart_remote(
    artifact: ChartArtifact,
    registry_url: str,
) -> str:
    """Push a chart to a remote OCI registry via oras-py.

    The tar.gz file is pushed as a single layer with custom media type.
    Chart metadata is stored in manifest annotations.
    """
    if not artifact.tar_path or not artifact.tar_path.exists():
        raise OCIError("No artifact tar.gz to push")

    target = _registry_to_oras_target(
        registry_url, artifact.name, artifact.version,
    )

    client = _get_oras_client()

    # Write chart config as a temp JSON file for the manifest config
    config_data = json.dumps(artifact.config or {}, indent=2)
    config_file = Path(tempfile.mkdtemp()) / "chart-config.json"
    config_file.write_text(config_data)

    # Prepare manifest annotations with chart metadata
    annotations = {
        "io.bow.chart.name": artifact.name,
        "io.bow.chart.version": artifact.version,
        "io.bow.chart.description": artifact.description or "",
        "io.bow.chart.digest": artifact.digest or "",
        "org.opencontainers.image.title": artifact.name,
        "org.opencontainers.image.version": artifact.version,
    }

    # Push the tar.gz as a file with custom media type
    # oras format: "filepath:mediaType"
    file_ref = f"{artifact.tar_path}:{CHART_CONTENT_MEDIA_TYPE}"

    try:
        # Change to temp dir so oras doesn't complain about path validation
        original_dir = os.getcwd()
        os.chdir(artifact.tar_path.parent)

        response = client.push(
            files=[file_ref],
            target=target,
            manifest_config=f"{config_file}:{CHART_CONFIG_MEDIA_TYPE}",
            manifest_annotations=annotations,
            disable_path_validation=True,
        )

        os.chdir(original_dir)

        if response.status_code not in (200, 201):
            raise OCIError(
                f"Push failed with status {response.status_code}: "
                f"{response.text}"
            )
    except OCIError:
        raise
    except Exception as e:
        raise OCIError(f"Push to {target} failed: {e}") from e

    ref = f"oci://{target}"
    return ref


def _pull_chart_remote(
    name: str,
    version: str,
    registry_url: str,
    cache_dir: str | Path,
) -> ChartArtifact:
    """Pull a chart from a remote OCI registry via oras-py."""
    target = _registry_to_oras_target(registry_url, name, version)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download dir for oras pull
    download_dir = Path(tempfile.mkdtemp())

    client = _get_oras_client()

    try:
        files = client.pull(
            target=target,
            outdir=str(download_dir),
        )
    except Exception as e:
        raise OCIError(f"Pull {target} failed: {e}") from e

    if not files:
        raise OCIError(f"No files in artifact {name}:{version}")

    # Find the tar.gz among pulled files
    tar_file = None
    config_data = {}
    for f in files:
        if f.endswith(".tar.gz"):
            tar_file = Path(f)
        elif f.endswith(".json"):
            try:
                config_data = json.loads(Path(f).read_text())
            except (json.JSONDecodeError, OSError):
                pass

    if tar_file is None:
        # If no tar.gz, take the first file
        tar_file = Path(files[0])

    # Copy to cache
    cache_tar = cache_dir / f"{name}-{version}.tar.gz"
    shutil.copy2(tar_file, cache_tar)

    # Compute digest
    digest = _compute_file_digest(cache_tar)

    # Try to get config from manifest annotations
    try:
        remote = client.remote
        manifest = remote.get_manifest(target)
        annots = manifest.get("annotations", {})
        description = annots.get("io.bow.chart.description", "")
        if not config_data:
            config_blob = manifest.get("config", {})
            if config_blob.get("mediaType") == CHART_CONFIG_MEDIA_TYPE:
                # Config is stored as a blob, try to read it
                pass
    except Exception:
        annots = {}
        description = config_data.get("description", "")

    return ChartArtifact(
        name=name,
        version=version,
        description=description,
        digest=digest,
        registry=registry_url,
        tar_path=cache_tar,
        config=config_data,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUBLIC API (routes local vs remote)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def push_chart(
    artifact: ChartArtifact,
    registry_url: str,
) -> str:
    """Push a chart to a registry.

    Routes to local filesystem or remote OCI registry based on URL.

    Returns:
        Full reference (oci://registry/name:version)
    """
    if _is_remote_registry(registry_url):
        return _push_chart_remote(artifact, registry_url)
    return _push_chart_local(artifact, registry_url)


def pull_chart(
    name: str,
    version: str,
    registry_url: str,
    cache_dir: str | Path,
) -> ChartArtifact:
    """Pull a chart from a registry.

    Routes to local filesystem or remote OCI registry based on URL.

    Returns:
        ChartArtifact (tar_path points to the cached file)
    """
    if _is_remote_registry(registry_url):
        return _pull_chart_remote(name, version, registry_url, cache_dir)
    return _pull_chart_local(name, version, registry_url, cache_dir)


def list_remote_charts(registry_url: str) -> list[dict[str, str]]:
    """List charts in a registry."""
    if _is_remote_registry(registry_url):
        return _list_remote_charts_oras(registry_url)
    return _list_remote_charts_local(registry_url)


def _list_remote_charts_local(registry_url: str) -> list[dict[str, str]]:
    """List charts in a local filesystem registry."""
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


def _list_remote_charts_oras(registry_url: str) -> list[dict[str, str]]:
    """List charts in a remote OCI registry via oras-py.

    Note: OCI Distribution Spec doesn't have a standard catalog/list API
    for all registries. This tries the _catalog endpoint.
    """
    try:
        client = _get_oras_client()
        url = registry_url.strip().rstrip("/")
        if url.startswith("oci://"):
            url = url[6:]

        remote = client.remote
        # Try to list tags for known chart names
        # OCI doesn't have a universal listing mechanism
        # This is a best-effort approach
        tags = remote.get_tags(url)
        charts = []
        for tag in tags:
            charts.append({"name": url.rsplit("/", 1)[-1], "version": tag})
        return charts
    except Exception:
        return []


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
