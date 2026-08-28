"""T1 - lifecycle dataclasses (MLC-01).

Tests are derived from the spec ACs and the task's "Done when":
- five dataclasses exist with the design's fields
- ModelState.from_dict accepts the real GET /v1/models payload, ignores extras
- a status outside {loaded, loading, unloaded} normalises to "unloaded"
"""

from homebench.lifecycle.models import (
    LifecycleOutcome,
    LifecyclePlan,
    LoadParams,
    ModelState,
    RouterInfo,
)


# ---- RouterInfo ----------------------------------------------------------
def test_routerinfo_parses_props_payload_and_ignores_unknown_keys():
    info = RouterInfo.from_dict(
        {
            "role": "router",
            "max_instances": 2,
            "models_autoload": False,
            "build_info": "b10615-f280b2698",
            "some_future_field": "ignored",
        }
    )
    assert info.role == "router"
    assert info.max_instances == 2
    assert info.models_autoload is False
    assert info.build_info == "b10615-f280b2698"


def test_routerinfo_defaults_are_empty():
    info = RouterInfo()
    assert info.role == ""
    assert info.max_instances == 0
    assert info.models_autoload is False
    assert info.build_info == ""


# ---- ModelState ---------------------------------------------------------
def _real_entry(model_id, value, args, preset="qwen35-4b", source="models_dir"):
    """One entry shaped like the router's real GET /v1/models payload."""
    return {
        "id": model_id,
        "object": "model",
        "created": 1730000000,
        "owned_by": "llamacpp",
        "source": source,
        "status": {"value": value, "args": args, "preset": preset},
    }


def test_modelstate_parses_real_v1_models_entry():
    entry = _real_entry(
        "qwen35-4b",
        "loaded",
        ["/app/llama-server", "-m", "/models/qwen35-4b.gguf", "-ngl", "99"],
        preset="qwen35-4b",
        source="models_dir",
    )
    st = ModelState.from_dict(entry)
    assert st.id == "qwen35-4b"
    assert st.status == "loaded"
    assert st.args == ["/app/llama-server", "-m", "/models/qwen35-4b.gguf", "-ngl", "99"]
    assert st.preset == "qwen35-4b"
    assert st.source == "models_dir"


def test_modelstate_ignores_unknown_keys():
    entry = _real_entry("m", "loading", ["-ngl", "10"])
    entry["brand_new_key"] = {"nested": 1}
    entry["status"]["another_new_key"] = 5
    st = ModelState.from_dict(entry)
    assert st.id == "m"
    assert st.status == "loading"
    assert st.args == ["-ngl", "10"]


def test_modelstate_unknown_status_normalises_to_unloaded():
    st = ModelState.from_dict(_real_entry("m", "evicting", ["-ngl", "1"]))
    assert st.status == "unloaded"


def test_modelstate_empty_status_normalises_to_unloaded():
    st = ModelState.from_dict({"id": "m", "status": {"value": "", "args": []}})
    assert st.status == "unloaded"


def test_modelstate_args_present_even_when_unloaded():
    # the router exposes the resolved preset argv cold, before the model loads
    st = ModelState.from_dict(_real_entry("m", "unloaded", ["-m", "/models/m.gguf", "-c", "8192"]))
    assert st.status == "unloaded"
    assert st.args == ["-m", "/models/m.gguf", "-c", "8192"]


def test_modelstate_round_trips_through_dict():
    st = ModelState(id="m", status="loaded", args=["-ngl", "5"], preset="p", source="models_dir")
    again = ModelState.from_dict(st.to_dict())
    assert again == st


# ---- LoadParams -------------------------------------------------------
def test_loadparams_defaults():
    lp = LoadParams()
    assert lp.extra_args == []
    assert lp.origin == "default"


def test_loadparams_round_trips_and_ignores_extras():
    lp = LoadParams(extra_args=["-ngl", "20"], origin="json")
    again = LoadParams.from_dict({**lp.to_dict(), "future": 1})
    assert again == lp


# ---- LifecyclePlan ---------------------------------------------------
def test_lifecycleplan_defaults():
    plan = LifecyclePlan(target="m")
    assert plan.target == "m"
    assert plan.to_unload == []
    assert plan.needs_load is True
    assert plan.reason == ""


# ---- LifecycleOutcome ----------------------------------------------
def test_lifecycleoutcome_carries_plan_and_effective_args():
    plan = LifecyclePlan(target="m", to_unload=["other"], needs_load=True, reason="load m")
    outcome = LifecycleOutcome(plan=plan, effective_args=["-ngl", "99"], unloaded=["other"])
    d = outcome.to_dict()
    assert d["plan"]["target"] == "m"
    assert d["effective_args"] == ["-ngl", "99"]
    assert d["unloaded"] == ["other"]
    assert LifecycleOutcome.from_dict(d) == outcome
