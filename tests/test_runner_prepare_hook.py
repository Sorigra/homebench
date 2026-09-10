"""The per-model preparation hook (Fix 1 for MLC-01/MLC-03/MLC-09).

The Runner calls ``prepare_model`` once per model, at the start of that
model's turn, so every measured model -- not just the first -- is made the
sole resident and has its effective load argv recorded. A ProviderError from
the hook fails only that model (MLC-11).
"""

import json

from homebench.models import ModelInfo
from homebench.providers.base import ProviderError
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider


def _runner(provider, hook, **cfg):
    cfg.setdefault("quick", False)
    return Runner(provider, RunConfig(sample_rss=False, warmup=False, **cfg),
                  prepare_model=hook)


def test_hook_is_called_once_per_model_in_order():
    provider = FakeProvider()
    calls = []
    runner = _runner(provider, lambda m: calls.append(m.name) or None)
    runner.run(provider.list_models())
    assert calls == ["fast:1b", "smart:8b"]


def test_every_model_records_its_effective_load_params_not_just_the_first():
    provider = FakeProvider()
    argv = {"fast:1b": ["-ngl", "10"], "smart:8b": ["-ngl", "20"]}
    runner = _runner(provider, lambda m: argv[m.name])
    result = runner.run(provider.list_models())
    assert result.config["load_params"] == argv


def test_hook_returning_none_records_nothing_for_that_model():
    provider = FakeProvider()
    runner = _runner(provider,
                     lambda m: ["-ngl", "10"] if m.name == "fast:1b" else None)
    result = runner.run(provider.list_models())
    assert result.config["load_params"] == {"fast:1b": ["-ngl", "10"]}


def test_base_config_load_params_are_merged_with_hook_results():
    provider = FakeProvider()
    runner = Runner(
        provider,
        RunConfig(sample_rss=False, warmup=False, quick=False,
                  load_params={"fast:1b": ["-from-config"]}),
        prepare_model=lambda m: ["-from-hook"] if m.name == "smart:8b" else None,
    )
    result = runner.run(provider.list_models())
    assert result.config["load_params"] == {
        "fast:1b": ["-from-config"], "smart:8b": ["-from-hook"],
    }


def test_hook_error_fails_only_that_model():
    provider = FakeProvider()

    def hook(m):
        if m.name == "fast:1b":
            raise ProviderError("router rejected -ngl 999")
        return None

    result = _runner(provider, hook).run(provider.list_models())
    by_name = {r.model.name: r for r in result.reports}
    assert "router rejected -ngl 999" in by_name["fast:1b"].error
    assert by_name["fast:1b"].speed.tokens_per_sec == 0.0     # never measured
    assert by_name["smart:8b"].error is None
    assert by_name["smart:8b"].speed.tokens_per_sec > 0       # still measured


def test_prepare_runs_before_warmup_for_every_model():
    provider = FakeProvider()
    events = []
    orig_warmup = provider.warmup

    def spy_warmup(model, **kw):
        events.append(("warmup", model))
        return orig_warmup(model, **kw)

    provider.warmup = spy_warmup
    runner = Runner(
        provider,
        RunConfig(sample_rss=False, warmup=True, run_quality=False, quick=False),
        prepare_model=lambda m: events.append(("prepare", m.name)) or None,
    )
    runner.run(provider.list_models())
    assert events == [
        ("prepare", "fast:1b"), ("warmup", "fast:1b"),
        ("prepare", "smart:8b"), ("warmup", "smart:8b"),
    ]


def test_prepare_phase_event_is_emitted_per_model():
    provider = FakeProvider()
    seen = []
    runner = _runner(provider, lambda m: None)
    runner.run(provider.list_models(),
               observer=lambda ev, **d: seen.append((ev, d)))
    prepared = [d["model"] for ev, d in seen
                if ev == "phase" and d.get("phase") == "prepare"]
    assert prepared == ["fast:1b", "smart:8b"]


def test_no_hook_means_no_prepare_phase_and_no_load_params():
    provider = FakeProvider()
    seen = []
    runner = Runner(provider, RunConfig(sample_rss=False, warmup=False, quick=False))
    result = runner.run(provider.list_models(),
                        observer=lambda ev, **d: seen.append((ev, d)))
    assert not [d for ev, d in seen if ev == "phase" and d.get("phase") == "prepare"]
    assert result.config["load_params"] == {}


def test_recorded_load_params_survive_the_json_round_trip():
    provider = FakeProvider()
    runner = _runner(provider, lambda m: ["-ngl", "42"])
    result = runner.run(provider.list_models())
    restored = json.loads(json.dumps(result.to_dict()))
    assert restored["config"]["load_params"]["smart:8b"] == ["-ngl", "42"]


# =====================================================================
# The argv the hook resolved also bounds the depth sweep (PERF-14)
# =====================================================================
def test_the_hooks_argv_bounds_the_depth_sweep_of_that_model():
    """A depth the backend's per-slot context cannot hold never gets sent."""
    provider = FakeProvider()
    argv = {"fast:1b": ["--ctx-size", "16384", "--parallel", "4"],
            "smart:8b": ["--ctx-size", "131072", "--parallel", "1"]}
    runner = _runner(provider, lambda m: argv[m.name],
                     run_quality=False, depths=[0, 8192])
    result = runner.run(provider.list_models())

    by_name = {r.model.name: r.depth_results for r in result.reports}
    # 16384/4 = 4096 usable: the 8k depth cannot fit.
    assert by_name["fast:1b"][1].skipped is not None
    assert "server context is 4096" in by_name["fast:1b"][1].skipped
    # 131072/1: it fits, so it is measured like any other depth.
    assert by_name["smart:8b"][1].skipped is None


def test_configured_load_params_bound_the_sweep_when_there_is_no_hook():
    provider = FakeProvider()
    runner = Runner(provider, RunConfig(
        sample_rss=False, warmup=False, quick=False, run_quality=False,
        depths=[0, 32768],
        load_params={"fast:1b": ["--ctx-size", "8192"]},
    ))
    result = runner.run([provider.list_models()[0]])

    assert result.reports[0].depth_results[1].skipped is not None


def test_a_model_without_resolved_argv_sweeps_every_depth():
    provider = FakeProvider()
    runner = _runner(provider, lambda m: None, run_quality=False,
                     depths=[0, 8192])
    result = runner.run([provider.list_models()[0]])

    assert [p.skipped for p in result.reports[0].depth_results] == [None, None]


def test_the_served_context_window_wins_over_the_launch_argv():
    """llama.cpp caps --ctx-size at the trained context and says nothing.

    The argv here asks for 133120 and the backend serves 131072, so a 131072
    depth (plus the 100 tokens the probe generates) does not fit. Trusting the
    argv would send it anyway and collect an HTTP 400.
    """
    provider = FakeProvider()
    provider.context_window = lambda model: 131072
    runner = _runner(provider, lambda m: ["--ctx-size", "133120", "--parallel", "1"],
                     run_quality=False, depths=[131072])
    result = runner.run([provider.list_models()[0]])

    skipped = result.reports[0].depth_results[0].skipped
    assert skipped is not None
    assert "server context is 131072" in skipped
    assert "served by the backend" in skipped


def test_the_argv_is_used_when_the_backend_cannot_report_its_context():
    provider = FakeProvider()
    provider.context_window = lambda model: None
    runner = _runner(provider, lambda m: ["--ctx-size", "8192", "--parallel", "2"],
                     run_quality=False, depths=[8192])
    result = runner.run([provider.list_models()[0]])

    assert "--ctx-size 8192 / --parallel 2" in result.reports[0].depth_results[0].skipped


def test_a_backend_that_raises_on_context_window_does_not_fail_the_model():
    def _boom(model):
        raise RuntimeError("no props route here")

    provider = FakeProvider()
    provider.context_window = _boom
    runner = _runner(provider, lambda m: None, run_quality=False, depths=[0])
    result = runner.run([provider.list_models()[0]])

    assert result.reports[0].error is None
    assert result.reports[0].depth_results[0].skipped is None
