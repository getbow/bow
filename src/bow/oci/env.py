"""
bow.oci.env — Environment (env) management.

Each env is an isolated venv. Charts are pip-installed
into the active env's venv.

~/.bow/
├── envs/
│   ├── default/
│   │   ├── venv/          ← Python venv
│   │   ├── cache/         ← OCI artifact cache
│   │   └── env.yaml       ← metadata
│   └── prod/
│       ├── venv/
│       ├── cache/
│       └── env.yaml
└── active → envs/default   ← symlink

Per-project override: .bowenv file
"""

from __future__ import annotations

import subprocess
import sys
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from bow.oci.config import BOW_HOME, load_config, save_config


ENVS_DIR = BOW_HOME / "envs"


@dataclass
class EnvInfo:
    """Env metadata."""
    name: str
    path: Path
    created: str | None = None
    description: str = ""

    @property
    def venv_path(self) -> Path:
        return self.path / "venv"

    @property
    def cache_path(self) -> Path:
        return self.path / "cache"

    @property
    def site_packages(self) -> Path:
        """The venv's site-packages directory."""
        vp = self.venv_path
        # Linux: lib/pythonX.Y/site-packages
        lib = vp / "lib"
        if lib.exists():
            for d in lib.iterdir():
                if d.name.startswith("python"):
                    sp = d / "site-packages"
                    if sp.exists():
                        return sp
        # Fallback
        return vp / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"

    @property
    def pip_path(self) -> Path:
        return self.venv_path / "bin" / "pip"

    @property
    def python_path(self) -> Path:
        return self.venv_path / "bin" / "python"

    def exists(self) -> bool:
        return self.path.exists() and self.venv_path.exists()


class EnvError(Exception):
    pass


def create_env(name: str, description: str = "") -> EnvInfo:
    """Create a new environment."""
    env_path = ENVS_DIR / name
    if env_path.exists():
        raise EnvError(f"Environment '{name}' already exists")

    env_path.mkdir(parents=True, exist_ok=True)

    # Create venv
    venv_path = env_path / "venv"
    venv.create(str(venv_path), with_pip=True, clear=True)

    # Install bow into the venv (not editable, just import path)
    # bow CLI runs on the host system; venv is only for charts
    # But bow is needed for entry_points to work
    _pip_install_bow(venv_path)

    # Cache dir
    (env_path / "cache").mkdir(exist_ok=True)

    # Metadata
    import datetime
    info = EnvInfo(
        name=name,
        path=env_path,
        created=datetime.datetime.now().isoformat(),
        description=description,
    )
    _save_env_meta(info)

    return info


def _pip_install_bow(venv_path: Path) -> None:
    """Install the bow package into the venv."""
    pip = venv_path / "bin" / "pip"
    # Find bow itself
    import bow
    bow_root = Path(bow.__file__).parent.parent.parent  # src/bow → src → project root
    # If editable install, pyproject.toml location
    pyproject = bow_root / "pyproject.toml"
    if pyproject.exists():
        subprocess.run(
            [str(pip), "install", "-e", str(bow_root), "-q"],
            capture_output=True, text=True,
        )
    else:
        # Fallback: pip install bow
        subprocess.run(
            [str(pip), "install", "bow", "-q"],
            capture_output=True, text=True,
        )


def delete_env(name: str) -> None:
    """Delete an environment."""
    if name == "default":
        raise EnvError("Cannot delete the default environment")

    env_path = ENVS_DIR / name
    if not env_path.exists():
        raise EnvError(f"Environment '{name}' not found")

    import shutil
    shutil.rmtree(env_path)

    # If the active env was deleted, fall back to default
    cfg = load_config()
    if cfg.active_env == name:
        cfg.active_env = "default"
        save_config(cfg)


def get_env(name: str | None = None) -> EnvInfo:
    """Get env info. If None, returns the active env."""
    if name is None:
        name = resolve_active_env()

    env_path = ENVS_DIR / name
    if not env_path.exists():
        # Auto-create default if it doesn't exist
        if name == "default":
            return create_env("default")
        raise EnvError(f"Environment '{name}' not found. Run: bow env create {name}")

    return EnvInfo(name=name, path=env_path)


def resolve_active_env() -> str:
    """Resolve the active env name.

    Priority:
      1. BOW_ENV env var
      2. .bowenv file (searched upward from cwd)
      3. ~/.bow/config.yaml active_env
      4. "default"
    """
    import os

    # 1. Env var
    env_var = os.environ.get("BOW_ENV", "").strip()
    if env_var:
        return env_var

    # 2. .bowenv file
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        bowenv = parent / ".bowenv"
        if bowenv.exists():
            content = bowenv.read_text().strip()
            if content:
                return content
        # Search up to /home or /
        if parent == Path.home() or parent == Path("/"):
            break

    # 3. Config
    cfg = load_config()
    return cfg.active_env or "default"


def use_env(name: str) -> None:
    """Switch the active environment."""
    env_path = ENVS_DIR / name
    if not env_path.exists():
        raise EnvError(f"Environment '{name}' not found. Run: bow env create {name}")

    cfg = load_config()
    cfg.active_env = name
    save_config(cfg)


def list_envs() -> list[EnvInfo]:
    """List all environments."""
    if not ENVS_DIR.exists():
        return []

    envs = []
    for d in sorted(ENVS_DIR.iterdir()):
        if d.is_dir() and (d / "venv").exists():
            envs.append(EnvInfo(name=d.name, path=d))
    return envs


def pip_install_in_env(
    package_path: str | Path,
    env: EnvInfo | None = None,
) -> subprocess.CompletedProcess:
    """Run pip install in the env's venv."""
    if env is None:
        env = get_env()

    pip = env.pip_path
    if not pip.exists():
        raise EnvError(f"pip not found in env '{env.name}': {pip}")

    return subprocess.run(
        [str(pip), "install", str(package_path), "-q"],
        capture_output=True, text=True,
    )


def _save_env_meta(info: EnvInfo) -> None:
    """Write env metadata."""
    meta_path = info.path / "env.yaml"
    data = {
        "name": info.name,
        "created": info.created,
        "description": info.description,
    }
    with open(meta_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
