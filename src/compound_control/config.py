from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]

    @property
    def currency(self) -> dict[str, Any]:
        return self.raw["currency"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.raw["risk"]

    @property
    def execution(self) -> dict[str, Any]:
        return self.raw["execution"]

    @property
    def partial_tp(self) -> dict[str, Any]:
        return self.raw["partial_tp"]


def load_config(path: str | Path = "config/settings.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    required = {"currency", "risk", "execution", "partial_tp"}
    missing = required.difference(raw or {})
    if missing:
        raise ConfigurationError(f"Missing config sections: {sorted(missing)}")
    return AppConfig(raw=raw)
