import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = REPO_ROOT / "setup.sh"


def _run_setup(*args, env=None, cwd=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SETUP_SH), *args],
        cwd=str(cwd or REPO_ROOT),
        env=merged,
        capture_output=True,
        text=True,
    )


def test_setup_script_has_no_forbidden_commands():
    content = SETUP_SH.read_text()
    for word in ("docker", "sudo", "systemctl"):
        assert word not in content


def test_setup_defaults_writes_config(monkeypatch, tmp_path):
    home = tmp_path / "operator-home"
    home.mkdir()
    bench_home = home / ".homebench"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HOMEBENCH_HOME", str(bench_home))
    monkeypatch.setenv("HOMEBENCH_SETUP_SKIP_PIP", "1")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = _run_setup("--defaults", cwd=elsewhere)
    assert result.returncode == 0, result.stderr

    config_path = bench_home / "config.json"
    assert config_path.is_file()
    data = json.loads(config_path.read_text())
    assert data["host"] == "http://127.0.0.1:8080"
    assert data["api_key_file"] == str(home / "llm-server" / "llama" / "api-key.txt")
    assert data["model_dir"] == "/home/eskudo/ai-models"
    assert "api_key" not in data


def test_setup_defaults_creates_launcher_wrapper(monkeypatch, tmp_path):
    home = tmp_path / "operator-home"
    home.mkdir()
    bench_home = home / ".homebench"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HOMEBENCH_HOME", str(bench_home))
    monkeypatch.setenv("HOMEBENCH_SETUP_SKIP_PIP", "1")

    result = _run_setup("--defaults")
    assert result.returncode == 0, result.stderr

    wrapper = home / ".local" / "bin" / "homebench"
    assert wrapper.is_file()
    text = wrapper.read_text()
    assert str(REPO_ROOT / ".venv" / "bin" / "homebench") in text
