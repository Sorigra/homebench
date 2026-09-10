"""Persistent Homebench settings under ``$HOMEBENCH_HOME/config.json``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .history import default_home

HOST_ENV = "LLAMACPP_HOST"
API_KEY_ENV = "LLAMACPP_API_KEY"
MODEL_DIR_ENV = "HOMEBENCH_MODEL_DIR"


@dataclass
class HomebenchConfig:
    host: str = "http://127.0.0.1:8080"
    api_key_file: str = ""
    model_dir: str = ""
    last_plan: Optional[dict] = field(default=None)


def read_api_key(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
    except OSError:
        return None
    return content or None


def apply_to_environ(cfg: HomebenchConfig) -> None:
    if not os.environ.get(HOST_ENV) and cfg.host:
        os.environ[HOST_ENV] = cfg.host
    if not os.environ.get(MODEL_DIR_ENV) and cfg.model_dir:
        os.environ[MODEL_DIR_ENV] = cfg.model_dir
    if not os.environ.get(API_KEY_ENV) and cfg.api_key_file:
        key = read_api_key(cfg.api_key_file)
        if key:
            os.environ[API_KEY_ENV] = key


def _config_path(home: Optional[str] = None) -> str:
    return os.path.join(home or default_home(), "config.json")


def load(home: Optional[str] = None) -> HomebenchConfig:
    path = _config_path(home)
    if not os.path.isfile(path):
        return HomebenchConfig()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return HomebenchConfig()
    if not isinstance(data, dict):
        return HomebenchConfig()
    return HomebenchConfig(
        host=data.get("host", "http://127.0.0.1:8080"),
        api_key_file=data.get("api_key_file", ""),
        model_dir=data.get("model_dir", ""),
        last_plan=data.get("last_plan"),
    )


def save(cfg: HomebenchConfig, home: Optional[str] = None) -> str:
    root = home or default_home()
    os.makedirs(root, exist_ok=True)
    path = _config_path(home)
    payload: Dict[str, Any] = {
        "host": cfg.host,
        "api_key_file": cfg.api_key_file,
        "model_dir": cfg.model_dir,
    }
    if cfg.last_plan is not None:
        payload["last_plan"] = cfg.last_plan
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path
