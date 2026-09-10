"""Persistent Homebench settings under ``$HOMEBENCH_HOME/config.json``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .history import default_home


@dataclass
class HomebenchConfig:
    host: str = "http://127.0.0.1:8080"
    api_key_file: str = ""
    model_dir: str = ""
    last_plan: Optional[dict] = field(default=None)


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
