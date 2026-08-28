"""The Runner drives the depth sweep (PERF-10, PERF-13, PERF-14, PERF-15).

Runner-level wiring only; the sweep itself is covered in test_depth_measure.py.
Uses FakeProvider, so nothing here reaches a backend.
"""

from homebench.providers.base import ProviderError
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider


def _run(provider, **cfg):
    cfg.setdefault("sample_rss", False)
    cfg.setdefault("warmup", False)
    cfg.setdefault("run_quality", False)
    runner = Runner(provider, RunConfig(**cfg))
    seen = []
    models = [provider.list_models()[0]]
    result = runner.run(models, observer=lambda ev, **d: seen.append((ev, d)))
    return result.reports[0], seen


class _DepthAware(FakeProvider):
    """Decode rate falls as the prompt grows, the way a real model behaves."""

    def generate(self, model, prompt, **kw):
        gen = super().generate(model, prompt, **kw)
        words = len(prompt.split())
        gen.speed.tokens_per_sec = 95.1 if words < 100 else (
            83.3 if words < 10_000 else 73.0)
        gen.speed.prompt_tokens = words
        return gen


class _NoRoom(_DepthAware):
    """Refuses the deepest prompt the way the router refuses an over-long one."""

    def generate(self, model, prompt, **kw):
        if len(prompt.split()) >= 10_000:
            raise ProviderError("llamacpp generate failed for 'fast:1b': the "
                                "request exceeds the available context size")
        return super().generate(model, prompt, **kw)


def test_run_config_sweeps_three_depths_by_default():
    cfg = RunConfig()
    assert cfg.depths == [0, 8192, 32768]
    assert cfg.to_dict()["depths"] == [0, 8192, 32768]


def test_the_report_records_one_depth_point_per_measured_depth():
    report, _ = _run(FakeProvider(), depths=[0, 64, 128])
    assert [p.depth_requested for p in report.depth_results] == [0, 64, 128]
    assert all(p.decode_tps > 0 and p.skipped is None for p in report.depth_results)

    shallow, _ = _run(FakeProvider(), depths=[0])
    assert [p.depth_requested for p in shallow.depth_results] == [0]


def test_report_speed_is_the_shallowest_measured_depth():
    report, _ = _run(_DepthAware(), depths=[32768, 8192, 0])
    assert [p.depth_requested for p in report.depth_results] == [32768, 8192, 0]
    # score.py, history and diff read this one number
    assert report.speed.tokens_per_sec == 95.1


def test_the_speed_phase_event_carries_the_current_depth():
    _, seen = _run(FakeProvider(), depths=[0, 64, 128])
    depths = [d["depth"] for ev, d in seen
              if ev == "phase" and d.get("phase") == "speed" and "depth" in d]
    assert depths == [0, 64, 128]


def test_a_skipped_depth_lands_on_the_report_warnings():
    report, seen = _run(_NoRoom(), depths=[0, 32768])

    assert report.error is None                       # the model did not fail
    assert report.depth_results[0].decode_tps == 95.1
    assert "exceeds the available context size" in report.depth_results[1].skipped
    assert len(report.warnings) == 1
    assert "32768" in report.warnings[0]
    assert "exceeds the available context size" in report.warnings[0]
    notes = [d["note"] for ev, d in seen
             if ev == "phase" and d.get("phase") == "warning"]
    assert notes == report.warnings
