import json
import os

import pytest

from homebench import config
from homebench.config import HomebenchConfig


def test_load_missing_file_returns_defaults(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    cfg = config.load()
    assert cfg.host == "http://127.0.0.1:8080"
    assert cfg.api_key_file == ""
    assert cfg.model_dir == ""
    assert cfg.last_plan is None


def test_load_invalid_json_returns_defaults(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "config.json"), "w") as f:
        f.write("{not valid json")
    cfg = config.load()
    assert cfg.host == "http://127.0.0.1:8080"
    assert cfg.api_key_file == ""
    assert cfg.model_dir == ""


def test_save_writes_fields_without_api_key(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    cfg = HomebenchConfig(
        host="http://192.168.1.10:8080",
        api_key_file="/tmp/two-keys/a.txt",
        model_dir="/tmp/two-models",
    )
    path = config.save(cfg)
    assert path == os.path.join(home, "config.json")
    with open(path) as f:
        data = json.load(f)
    assert data["host"] == "http://192.168.1.10:8080"
    assert data["api_key_file"] == "/tmp/two-keys/a.txt"
    assert data["model_dir"] == "/tmp/two-models"
    assert "api_key" not in data


def test_save_round_trip(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    original = HomebenchConfig(
        host="http://127.0.0.1:9090",
        api_key_file="/path/to/key.txt",
        model_dir="/path/to/models",
        last_plan={"model_ids": ["a", "b"], "depths": [0, 8192]},
    )
    config.save(original)
    loaded = config.load()
    assert loaded.host == original.host
    assert loaded.api_key_file == original.api_key_file
    assert loaded.model_dir == original.model_dir
    assert loaded.last_plan == original.last_plan
