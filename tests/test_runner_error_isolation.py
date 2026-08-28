"""A mid-run ProviderError fails only the current model (MLC-11).

Covers the spec edge case "IF o container do router reiniciar durante a
medição THEN o sistema SHALL falhar o modelo corrente com ProviderError sem
abortar os demais modelos do run." The isolation lives in
``Runner._run_model``; nothing asserted it before.
"""

from homebench.models import ModelInfo
from homebench.providers.base import GenerationResult, ProviderError
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider

THREE = [ModelInfo(n, "llamacpp") for n in ("a:1b", "b:1b", "c:1b")]


class _FlakyProvider(FakeProvider):
    """Raises ProviderError for one model, as if the backend went away."""

    def __init__(self, broken: str):
        super().__init__(models=list(THREE),
                         tps={"a:1b": 100.0, "b:1b": 100.0, "c:1b": 100.0})
        self._broken = broken

    def generate(self, model, prompt, **kw):
        if model == self._broken:
            raise ProviderError("connection refused: router restarting")
        return super().generate(model, prompt, **kw)


def _run(broken):
    provider = _FlakyProvider(broken)
    runner = Runner(provider, RunConfig(sample_rss=False, warmup=False,
                                        run_quality=False, quick=False))
    seen = []
    result = runner.run(THREE, observer=lambda ev, **d: seen.append((ev, d)))
    return result, seen


def test_the_broken_model_is_flagged_and_the_others_still_measure():
    result, _ = _run("b:1b")
    by_name = {r.model.name: r for r in result.reports}

    assert len(result.reports) == 3
    assert "connection refused: router restarting" in by_name["b:1b"].error
    assert by_name["b:1b"].speed.tokens_per_sec == 0.0

    assert by_name["a:1b"].error is None
    assert by_name["c:1b"].error is None
    assert by_name["a:1b"].speed.tokens_per_sec > 0
    assert by_name["c:1b"].speed.tokens_per_sec > 0


def test_an_error_phase_event_is_emitted_only_for_the_broken_model():
    _, seen = _run("c:1b")
    errored = [d["model"] for ev, d in seen
               if ev == "phase" and d.get("phase") == "error"]
    assert errored == ["c:1b"]


def test_the_run_still_completes():
    _, seen = _run("a:1b")
    assert [ev for ev, _ in seen if ev in ("run_start", "run_done")] == [
        "run_start", "run_done"]
