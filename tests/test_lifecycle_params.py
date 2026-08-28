"""Load-parameter resolution (T6-T8).

MLC-09 (effective params recorded, runs distinguishable), MLC-13 (extra_args
passed through unvalidated; malformed override file degrades, never aborts).
"""

import json

import pytest

from homebench.hardware import GPUInfo, HardwareInfo
from homebench.lifecycle.models import ModelState
from homebench.lifecycle.params import (
    NGL_ALL,
    default_home,
    load_overrides,
    suggest_ngl,
)

GB = 1_000_000_000


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


# =====================================================================
# T7: suggest_ngl()
# =====================================================================
def test_model_that_fits_comfortably_suggests_full_offload():
    hw = HardwareInfo(os="Linux", ram_total_bytes=64 * GB,
                      gpu=GPUInfo(name="RTX 4090", vram_bytes=24 * GB, kind="nvidia"))
    budget, _ = hw.memory_budget()          # 0.90 * 24 GB
    assert suggest_ngl(4 * GB, budget) == NGL_ALL


def test_model_larger_than_budget_suggests_zero():
    hw = HardwareInfo(os="Linux", ram_total_bytes=16 * GB)
    budget, _ = hw.memory_budget()          # 0.72 * 16 GB ~= 11.5 GB
    assert suggest_ngl(40 * GB, budget) == 0


def test_zero_budget_returns_zero():
    assert suggest_ngl(4 * GB, 0) == 0


def test_negative_budget_returns_zero():
    assert suggest_ngl(4 * GB, -5) == 0


def test_unknown_file_size_returns_zero():
    assert suggest_ngl(0, 24 * GB) == 0


def test_partial_fit_returns_value_between_zero_and_all():
    # weights are smaller than the budget but headroom pushes past it
    budget = 10 * GB
    ngl = suggest_ngl(9 * GB, budget)
    assert 0 < ngl < NGL_ALL


def test_result_is_always_non_negative_int():
    for fb, bg in [(0, 0), (1, 1), (5 * GB, 3 * GB), (3 * GB, 5 * GB)]:
        r = suggest_ngl(fb, bg)
        assert isinstance(r, int) and r >= 0
