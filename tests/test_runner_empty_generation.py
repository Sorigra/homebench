"""A generation that produced nothing is flagged, not reported as 0.00 (PERF-05).

Spec P1 AC5: zero tokens in *both* content and reasoning_content is a failure
and must say so. Tokens that arrived only as reasoning_content are a valid
measurement -- that is the whole point of P1 -- and must stay silent.
"""

import io
import json

from rich.console import Console

from homebench.models import BenchmarkResult
from homebench.plainui import run_plain
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider


class _Silent(FakeProvider):
    """Streams nothing at all: no content and no reasoning_content."""

    def generate(self, model, prompt, **kw):
        gen = super().generate(model, prompt, **kw)
        gen.text = ""
        gen.speed.output_tokens = 0
        gen.speed.content_tokens = 0
        gen.speed.reasoning_tokens = 0
        gen.speed.tokens_per_sec = 0.0
        return gen


class _ReasoningOnly(FakeProvider):
    """Every token arrives in reasoning_content; content stays empty."""

    def generate(self, model, prompt, **kw):
        gen = super().generate(model, prompt, **kw)
        gen.speed.reasoning_tokens = gen.speed.output_tokens
        gen.speed.content_tokens = 0
        gen.text = ""
        return gen


def _run(provider, **cfg):
    cfg.setdefault("sample_rss", False)
    cfg.setdefault("warmup", False)
    cfg.setdefault("run_quality", False)
    runner = Runner(provider, RunConfig(**cfg))
    seen = []
    result = runner.run([provider.list_models()[0]],
                        observer=lambda ev, **d: seen.append((ev, d)))
    return result.reports[0], seen


def test_an_empty_generation_warns_with_the_model_and_depth():
    report, seen = _run(_Silent(), depths=[0, 64])

    assert report.error is None                      # not a failure of the model
    assert len(report.warnings) == 2
    assert all("fast:1b" in w and "no tokens" in w for w in report.warnings)
    assert [w for w in report.warnings if "depth 0" in w]
    assert [w for w in report.warnings if "depth 64" in w]

    notes = [d["note"] for ev, d in seen
             if ev == "phase" and d.get("phase") == "warning"]
    assert notes == report.warnings


def test_a_reasoning_only_generation_is_not_flagged_as_empty():
    report, _ = _run(_ReasoningOnly(), depths=[0])

    assert report.warnings == []                     # a valid measurement
    assert report.speed.reasoning_tokens > 0
    assert report.speed.tokens_per_sec > 0
    assert report.depth_results[0].output_tokens > 0


def test_the_empty_generation_warning_survives_json_and_reaches_the_leaderboard():
    provider = _Silent()
    runner = Runner(provider, RunConfig(sample_rss=False, warmup=False,
                                        run_quality=False, depths=[0]))
    console = Console(file=io.StringIO(), width=120, force_terminal=False)

    result = run_plain(runner, [provider.list_models()[0]], console)

    assert "no tokens" in console.file.getvalue()    # printed after the leaderboard
    restored = BenchmarkResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored.reports[0].warnings == result.reports[0].warnings
    assert "depth 0" in restored.reports[0].warnings[0]
