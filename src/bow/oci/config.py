"""
bow.oci.config — Global config management.

~/.bow/config.yaml:

    registries:
      default:
        url: oci://ghcr.io/myorg/charts
        default: true
      harbor:
        url: oci://harbor.internal/bow

    security:
      allowed_registries:
        - oci://ghcr.io/myorg/charts
        - oci://harbor.internal/bow

    active_env: default
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


BOW_HOME = Path.home() / ".bow"


@dataclass
class RegistryConfig:
    """A single registry definition."""
    name: str
    url: str
    default: bool = False


@dataclass
class BowConfig:
    """Global bow config."""
    registries: dict[str, RegistryConfig] = field(default_factory=dict)
    allowed_registries: list[str] = field(default_factory=list)
    active_env: str = "default"

    def default_registry(self) -> RegistryConfig | None:
        for r in self.registries.values():
            if r.default:
                return r
        # Fall back to the first registry
        if self.registries:
            return next(iter(self.registries.values()))
        return None

    def is_registry_allowed(self, url: str) -> bool:
        """Check if registry URL is in the whitelist."""
        if not self.allowed_registries:
            return True  # Empty whitelist allows all
        normalized = url.rstrip("/")
        return any(
            normalized.startswith(allowed.rstrip("/"))
            for allowed in self.allowed_registries
        )


def config_path() -> Path:
    return BOW_HOME / "config.yaml"


def load_config() -> BowConfig:
    """Read ~/.bow/config.yaml."""
    cp = config_path()
    if not cp.exists():
        return BowConfig()

    with open(cp) as f:
        data = yaml.safe_load(f) or {}

    cfg = BowConfig()
    cfg.active_env = data.get("active_env", "default")

    # Registries
    for name, info in data.get("registries", {}).items():
        if isinstance(info, dict):
            cfg.registries[name] = RegistryConfig(
                name=name,
                url=info.get("url", ""),
                default=info.get("default", False),
            )

    # Security
    security = data.get("security", {})
    cfg.allowed_registries = security.get("allowed_registries", [])

    return cfg


def save_config(cfg: BowConfig) -> None:
    """Write ~/.bow/config.yaml."""
    BOW_HOME.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}

    if cfg.active_env != "default":
        data["active_env"] = cfg.active_env

    if cfg.registries:
        data["registries"] = {}
        for name, reg in cfg.registries.items():
            entry: dict[str, Any] = {"url": reg.url}
            if reg.default:
                entry["default"] = True
            data["registries"][name] = entry

    if cfg.allowed_registries:
        data["security"] = {
            "allowed_registries": cfg.allowed_registries,
        }

    with open(config_path(), "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
