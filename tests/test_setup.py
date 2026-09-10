import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = REPO_ROOT / "setup.sh"


def _run_setup(*args, env=None, cwd=None, script=SETUP_SH):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(cwd or REPO_ROOT),
        env=merged,
        capture_output=True,
        text=True,
    )


def _isolated_env(monkeypatch, tmp_path):
    home = tmp_path / "operator-home"
    home.mkdir()
    bench_home = home / ".homebench"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HOMEBENCH_HOME", str(bench_home))
    monkeypatch.setenv("HOMEBENCH_SETUP_SKIP_PIP", "1")
    return home, bench_home


def _fake_old_python(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "python3"
    fake.write_text(
        """#!/bin/sh
if [ "$1" = "-" ]; then
  cat >/dev/null
  exit 1
fi
if [ "$1" = "-m" ]; then
  exit 1
fi
exec /usr/bin/env python3 "$@"
"""
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return bindir


def _copy_setup_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(SETUP_SH, repo / "setup.sh")
    return repo


def test_setup_script_has_no_forbidden_commands():
    content = SETUP_SH.read_text()
    for word in ("docker", "sudo", "systemctl"):
        assert word not in content


def test_setup_defaults_writes_config(monkeypatch, tmp_path):
    home, bench_home = _isolated_env(monkeypatch, tmp_path)

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


def test_setup_defaults_via_absolute_path(monkeypatch, tmp_path):
    _home, bench_home = _isolated_env(monkeypatch, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run_setup("--defaults", cwd=elsewhere, script=SETUP_SH.resolve())
    assert result.returncode == 0, result.stderr
    assert (bench_home / "config.json").is_file()


def test_setup_defaults_is_idempotent(monkeypatch, tmp_path):
    _home, bench_home = _isolated_env(monkeypatch, tmp_path)

    first = _run_setup("--defaults")
    second = _run_setup("--defaults")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (bench_home / "config.json").is_file()


def test_setup_succeeds_when_doctor_fails(monkeypatch, tmp_path):
    _home, bench_home = _isolated_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLAMACPP_HOST", "http://127.0.0.1:9")

    result = _run_setup("--defaults")
    assert result.returncode == 0, result.stderr
    assert (bench_home / "config.json").is_file()
    assert "router check failed" in result.stderr


def test_setup_rejects_python_below_39(tmp_path):
    repo = _copy_setup_repo(tmp_path)
    fake_bin = _fake_old_python(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOMEBENCH_SETUP_SKIP_PIP"] = "1"

    result = _run_setup("--defaults", env=env, cwd=repo, script=repo / "setup.sh")
    assert result.returncode != 0
    assert not (repo / ".venv").exists()


def test_setup_defaults_creates_launcher_wrapper(monkeypatch, tmp_path):
    home, _bench_home = _isolated_env(monkeypatch, tmp_path)

    result = _run_setup("--defaults")
    assert result.returncode == 0, result.stderr

    wrapper = home / ".local" / "bin" / "homebench"
    assert wrapper.is_file()
    text = wrapper.read_text()
    assert str(REPO_ROOT / ".venv" / "bin" / "homebench") in text
