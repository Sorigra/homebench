"""Load-parameter resolution (T6-T8).

MLC-09 (effective params recorded, runs distinguishable), MLC-13 (extra_args
passed through unvalidated; malformed override file degrades, never aborts).
"""

import json

import pytest

from homebench.lifecycle.models import ModelState
from homebench.lifecycle.params import default_home, load_overrides


# =====================================================================
# T6: load_overrides()
# =====================================================================
def test_missing_file_returns_empty_dict(tmp_path):
    assert load_overrides(str(tmp_path / "nope.json")) == {}


def test_valid_file_is_parsed(tmp_path):
    p = tmp_path / "load-params.json"
    p.write_text(json.dumps({"qwen35-4b": ["-ngl", "20"], "gemma2-27b": ["-ngl", "46"]}))
    assert load_overrides(str(p)) == {
        "qwen35-4b": ["-ngl", "20"],
        "gemma2-27b": ["-ngl", "46"],
    }


def test_malformed_json_returns_empty_and_warns_without_raising(tmp_path):
    p = tmp_path / "load-params.json"
    p.write_text("{not valid json")
    with pytest.warns(UserWarning):
        result = load_overrides(str(p))
    assert result == {}


def test_non_object_json_returns_empty_and_warns(tmp_path):
    p = tmp_path / "load-params.json"
    p.write_text(json.dumps(["-ngl", "20"]))
    with pytest.warns(UserWarning):
        result = load_overrides(str(p))
    assert result == {}


def test_default_path_is_homebench_home_load_params_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    (tmp_path / "load-params.json").write_text(json.dumps({"m": ["-fa"]}))
    assert load_overrides() == {"m": ["-fa"]}
    assert default_home() == str(tmp_path)


def test_default_path_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    assert load_overrides() == {}
