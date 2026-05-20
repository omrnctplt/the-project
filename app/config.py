"""Konfigurasyon ve katalog yukleme/kaydetme."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Any

import yaml

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", "/etc/onprem-ai"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))

CATALOG_PATH = CONFIG_DIR / "model_catalog.yaml"
DEFAULT_USERS_PATH = CONFIG_DIR / "default_users.yaml"
RUNTIME_CONFIG_PATH = DATA_DIR / "runtime_config.yaml"

VALID_PROFILES = ("auto", "lite", "balanced", "performance")

_lock = RLock()


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Konfigurasyon dosyasi yok: {path}")
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Konfigurasyon dosyasi YAML map degil: {path}")
    return data


def load_catalog() -> dict[str, Any]:
    return _read_yaml(CATALOG_PATH)


def load_default_users() -> dict[str, Any]:
    return _read_yaml(DEFAULT_USERS_PATH)


def default_runtime_config() -> dict[str, Any]:
    return {
        "profile": os.getenv("CAPACITY_PROFILE", "auto"),
        "expected_users": 10,
        "expected_concurrency": 1,
        "auto_pull": os.getenv("AUTO_PULL_MODELS", "false").lower() == "true",
        "idle_unload_minutes": int(os.getenv("IDLE_UNLOAD_MINUTES", "3")),
        "active_models": [],
        "manual_override": False,
        "first_run_complete": False,
    }


def load_runtime_config() -> dict[str, Any]:
    with _lock:
        if not RUNTIME_CONFIG_PATH.exists():
            cfg = default_runtime_config()
            save_runtime_config(cfg)
            return cfg
        try:
            raw = RUNTIME_CONFIG_PATH.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        merged = default_runtime_config()
        for k, v in data.items():
            if k in merged:
                merged[k] = v
        if merged.get("profile") not in VALID_PROFILES:
            merged["profile"] = "auto"
        return merged


def save_runtime_config(cfg: dict[str, Any]) -> None:
    with _lock:
        RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RUNTIME_CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(
            yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        tmp.replace(RUNTIME_CONFIG_PATH)


def update_runtime_config(**changes: Any) -> dict[str, Any]:
    cfg = load_runtime_config()
    for key, value in changes.items():
        if key not in cfg:
            continue
        if key == "profile" and value not in VALID_PROFILES:
            continue
        cfg[key] = value
    save_runtime_config(cfg)
    return cfg
