"""Effective load parameters travel from RunConfig into the saved run (MLC-09).

Also guards the manual allowlist in ``RunConfig.to_dict()``: a field added to
the dataclass and forgotten there would vanish from every report and saved run
(design.md, Risks & Concerns).
"""

import json
from dataclasses import fields

from homebench.history import list_runs, save_run
from homebench.models import BenchmarkResult, ModelInfo, ModelReport, SpeedMetrics
from homebench.runner import RunConfig

#: Fields deliberately left out of ``to_dict()``. Anything else must be
#: serialised, or this list must grow on purpose -- that decision is the point
#: of the guard below.
NOT_SERIALISED = {
    "suite",          # list of Task objects; not JSON-serialisable
    "speed_prompt",   # long constant prompt text, not a knob worth storing
    # pre-existing omissions, kept as-is so this feature changes no behaviour
    "timeout",
    "use_cache",
    "refresh_cache",
}


def _result(load_params):
    cfg = RunConfig(load_params=load_params)
    result = BenchmarkResult(provider="llamacpp", config=cfg.to_dict())
    report = ModelReport(model=ModelInfo("qwen35-4b", "llamacpp"))
    report.speed = SpeedMetrics(tokens_per_sec=42.0)
    result.reports.append(report)
    return result


# ---- the field exists and is serialised ------------------------------------
def test_runconfig_has_a_load_params_field():
    assert "load_params" in {f.name for f in fields(RunConfig)}
    assert RunConfig().load_params is None


def test_load_params_appears_in_to_dict():
    cfg = RunConfig(load_params={"qwen35-4b": ["-ngl", "99"]})
    assert cfg.to_dict()["load_params"] == {"qwen35-4b": ["-ngl", "99"]}


def test_load_params_defaults_to_an_empty_mapping_in_to_dict():
    assert RunConfig().to_dict()["load_params"] == {}


# ---- anti-drift guard on the manual allowlist ------------------------------
def test_to_dict_serialises_every_runconfig_field():
    names = {f.name for f in fields(RunConfig)}
    assert names - NOT_SERIALISED == set(RunConfig().to_dict())


def test_the_exclusion_list_only_names_real_fields():
    # a stale exclusion would silently re-open the drift it was meant to close
    assert NOT_SERIALISED <= {f.name for f in fields(RunConfig)}


# ---- distinguishable in the saved history ----------------------------------
def test_two_runs_with_different_ngl_are_distinguishable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    save_run(_result({"qwen35-4b": ["-ngl", "99"]}), label="full-offload")
    save_run(_result({"qwen35-4b": ["-ngl", "20"]}), label="partial-offload")

    saved = [r.data["config"]["load_params"]["qwen35-4b"] for r in list_runs()]
    assert sorted(saved) == [["-ngl", "20"], ["-ngl", "99"]]


def test_load_params_survive_json_round_trip():
    result = _result({"qwen35-4b": ["-ngl", "20", "-fa"]})
    restored = BenchmarkResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored.config["load_params"] == {"qwen35-4b": ["-ngl", "20", "-fa"]}


def test_old_runs_without_load_params_still_load():
    old = _result(None).to_dict()
    del old["config"]["load_params"]           # a run saved before this feature
    restored = BenchmarkResult.from_dict(old)
    assert "load_params" not in restored.config
    assert restored.reports[0].model.name == "qwen35-4b"
