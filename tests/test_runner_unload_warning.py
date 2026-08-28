"""A best-effort unload failure is recorded where the run can report it (MLC-14 AC2).

The run must not stop; the failure lands on ``ModelReport.warnings`` (so it
survives into the saved run and the leaderboard) and is emitted as a
``phase="warning"`` observer event for the live renderers.
"""

import io
import json

from rich.console import Console

from homebench.models import BenchmarkResult, ModelInfo
from homebench.plainui import run_plain
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider


class _UnloadFailsProvider(FakeProvider):
    """Records an unload failure the way the llamacpp router provider does."""

    def __init__(self, failing: set):
        super().__init__()
        self._failing = failing
        self.last_unload_error = None

    def unload(self, model: str) -> None:
        self.unloaded.append(model)
        if model in self._failing:
            self.last_unload_error = f"router said no for {model}"
        else:
            self.last_unload_error = None


def _run(provider, **cfg):
    cfg.setdefault("quick", False)
    runner = Runner(provider, RunConfig(sample_rss=False, **cfg))
    seen = []
    result = runner.run(provider.list_models(),
                        observer=lambda ev, **d: seen.append((ev, d)))
    return result, seen


def test_unload_failure_is_recorded_on_the_report_warnings():
    result, _ = _run(_UnloadFailsProvider({"fast:1b"}))
    by_name = {r.model.name: r for r in result.reports}
    assert by_name["fast:1b"].warnings == ["unload failed: router said no for fast:1b"]
    assert by_name["fast:1b"].error is None            # the run did not fail
    assert by_name["smart:8b"].warnings == []          # its unload succeeded


def test_unload_failure_emits_a_warning_phase_event():
    _, seen = _run(_UnloadFailsProvider({"fast:1b"}))
    warnings = [d for ev, d in seen if ev == "phase" and d.get("phase") == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["model"] == "fast:1b"
    assert "router said no for fast:1b" in warnings[0]["note"]


def test_clean_unload_leaves_no_warning():
    result, seen = _run(_UnloadFailsProvider(set()))
    assert all(r.warnings == [] for r in result.reports)
    assert not [d for ev, d in seen if ev == "phase" and d.get("phase") == "warning"]


def test_no_warning_when_unload_between_is_disabled():
    result, _ = _run(_UnloadFailsProvider({"fast:1b", "smart:8b"}), unload_between=False)
    assert all(r.warnings == [] for r in result.reports)


def test_warnings_survive_json_round_trip():
    result, _ = _run(_UnloadFailsProvider({"fast:1b"}))
    restored = BenchmarkResult.from_dict(json.loads(json.dumps(result.to_dict())))
    by_name = {r.model.name: r for r in restored.reports}
    assert by_name["fast:1b"].warnings == ["unload failed: router said no for fast:1b"]


def test_old_reports_without_warnings_still_load():
    d = {"model": ModelInfo("m", "ollama").to_dict()}   # a report saved before this field
    from homebench.models import ModelReport
    assert ModelReport.from_dict(d).warnings == []


def test_plainui_prints_the_warning_after_the_leaderboard():
    provider = _UnloadFailsProvider({"fast:1b"})
    console = Console(file=io.StringIO(), width=100, force_terminal=False)
    runner = Runner(provider, RunConfig(sample_rss=False, quick=False))
    run_plain(runner, provider.list_models(), console)
    out = console.file.getvalue()
    assert "warning" in out and "router said no for fast:1b" in out
