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


def test_read_api_key_strips_content(tmp_path):
    key_file = tmp_path / "key.txt"
    key_file.write_text("  sk-two-keys  \n")
    assert config.read_api_key(str(key_file)) == "sk-two-keys"


def test_read_api_key_missing_file_returns_none(tmp_path):
    assert config.read_api_key(str(tmp_path / "missing.txt")) is None


def _snapshot_env(names):
    return {name: os.environ.get(name) for name in names}


def _restore_env(snapshot):
    for name, value in snapshot.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def test_apply_to_environ_fills_empty_vars(monkeypatch, tmp_path):
    env_names = (config.HOST_ENV, config.API_KEY_ENV, config.MODEL_DIR_ENV)
    saved = _snapshot_env(env_names)
    try:
        key_file = tmp_path / "api-key.txt"
        key_file.write_text("sk-from-file")
        for name in env_names:
            monkeypatch.delenv(name, raising=False)
        cfg = HomebenchConfig(
            host="http://10.0.0.1:8080",
            api_key_file=str(key_file),
            model_dir="/data/two-models",
        )
        config.apply_to_environ(cfg)
        assert os.environ[config.HOST_ENV] == "http://10.0.0.1:8080"
        assert os.environ[config.API_KEY_ENV] == "sk-from-file"
        assert os.environ[config.MODEL_DIR_ENV] == "/data/two-models"
    finally:
        _restore_env(saved)


def test_apply_to_environ_does_not_overwrite_existing(monkeypatch, tmp_path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("sk-from-file")
    monkeypatch.setenv(config.HOST_ENV, "http://existing:8080")
    monkeypatch.setenv(config.API_KEY_ENV, "sk-existing")
    monkeypatch.setenv(config.MODEL_DIR_ENV, "/existing/models")
    cfg = HomebenchConfig(
        host="http://10.0.0.1:8080",
        api_key_file=str(key_file),
        model_dir="/data/two-models",
    )
    config.apply_to_environ(cfg)
    assert os.environ[config.HOST_ENV] == "http://existing:8080"
    assert os.environ[config.API_KEY_ENV] == "sk-existing"
    assert os.environ[config.MODEL_DIR_ENV] == "/existing/models"


def test_apply_to_environ_skips_api_key_when_file_missing(monkeypatch, tmp_path):
    env_names = (config.HOST_ENV, config.API_KEY_ENV, config.MODEL_DIR_ENV)
    saved = _snapshot_env(env_names)
    try:
        for name in env_names:
            monkeypatch.delenv(name, raising=False)
        cfg = HomebenchConfig(api_key_file=str(tmp_path / "missing.txt"))
        config.apply_to_environ(cfg)
        assert config.API_KEY_ENV not in os.environ
    finally:
        _restore_env(saved)

