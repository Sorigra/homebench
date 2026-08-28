"""The context-depth sweep (PERF-10, PERF-13, PERF-14, PERF-15).

Offline by construction: the provider is injected and canned, so nothing here
opens a socket or touches the live router.
"""

import pytest

from homebench.metrics.depth import measure_at_depths
from homebench.models import ModelInfo, SpeedMetrics
from homebench.providers.base import GenerationResult, Provider, ProviderError
from homebench.runner import RunConfig

_SPEED_PROMPT = "Write a paragraph about how a CPU runs a program."


def _cfg(**kw):
    kw.setdefault("speed_prompt", _SPEED_PROMPT)
    return RunConfig(**kw)


def _result(*, prompt_tokens, decode, prefill=None, ttft=0.1,
            prompt_eval_s=0.0, out=100, cache_n=0):
    """A generation the way the llama.cpp router reports one."""
    speed = SpeedMetrics(
        ttft_s=ttft, tokens_per_sec=decode, prompt_tokens=prompt_tokens,
        output_tokens=out, prompt_eval_s=prompt_eval_s, prefill_tps=prefill,
        timings_source="server",
    )
    return GenerationResult(text="x", speed=speed, cache_hit_tokens=cache_n)


class _Recorder(Provider):
    """Provider that records every call and answers from a canned function."""

    name = "llamacpp"

    def __init__(self, respond):
        self._respond = respond
        self.calls = []

    def is_available(self):
        return True

    def list_models(self):
        return [ModelInfo("m", "llamacpp")]

    def generate(self, model, prompt, *, max_tokens=256, temperature=0.0,
                 seed=None, on_token=None, timeout=300.0, cache_prompt=True):
        self.calls.append({"prompt": prompt, "cache_prompt": cache_prompt})
        return self._respond(len(self.calls) - 1, prompt)


def _depth_of(prompt):
    """Which requested depth a synthesised prompt belongs to."""
    if prompt == _SPEED_PROMPT:
        return 0
    return 8192 if len(prompt.split()) < 10_000 else 32768


# =====================================================================
# PERF-10: one measurement per requested depth
# =====================================================================
def test_one_point_per_requested_depth_in_the_given_order():
    decodes = [95.1, 83.3, 73.0]
    prompts = [22, 8190, 32700]
    rec = _Recorder(lambda i, p: _result(prompt_tokens=prompts[i], decode=decodes[i]))

    sweep = measure_at_depths(rec, "gemma4-e2b", [0, 8192, 32768], cfg=_cfg())

    assert [pt.depth_requested for pt in sweep.points] == [0, 8192, 32768]
    assert [pt.decode_tps for pt in sweep.points] == [95.1, 83.3, 73.0]


# =====================================================================
# PERF-13: what a depth point records
# =====================================================================
def test_depth_actual_comes_from_the_server_not_the_target():
    rec = _Recorder(lambda i, p: _result(prompt_tokens=8190, decode=83.3))

    pt = measure_at_depths(rec, "m", [8192], cfg=_cfg()).points[0]

    assert pt.depth_requested == 8192
    assert pt.depth_actual == 8190        # prompt_n, never the number asked for


def test_each_point_records_prefill_decode_ttft_and_prompt_eval():
    rec = _Recorder(lambda i, p: _result(prompt_tokens=8190, decode=83.3,
                                         prefill=2709.0, ttft=0.42,
                                         prompt_eval_s=3.02, out=128))

    pt = measure_at_depths(rec, "m", [8192], cfg=_cfg()).points[0]

    assert pt.prefill_tps == 2709.0
    assert pt.decode_tps == 83.3
    assert pt.ttft_s == 0.42
    assert pt.prompt_eval_s == 3.02
    assert pt.output_tokens == 128
    assert pt.depth_actual == 8190
    assert pt.skipped is None


def test_every_measurement_generation_disables_prompt_caching():
    rec = _Recorder(lambda i, p: _result(prompt_tokens=10, decode=50.0))

    measure_at_depths(rec, "m", [0, 128], cfg=_cfg(repeat=2))

    assert len(rec.calls) == 4
    assert [c["cache_prompt"] for c in rec.calls] == [False, False, False, False]


def test_repeat_repeats_inside_each_depth_and_keeps_the_best():
    rates = {0: [(90.0, 0.30), (95.1, 0.10), (92.0, 0.20)],
             8192: [(80.0, 0.60), (83.3, 0.40), (81.0, 0.50)]}
    seen = []

    def respond(i, prompt):
        depth = _depth_of(prompt)
        decode, ttft = rates[depth][seen.count(depth)]
        seen.append(depth)
        return _result(prompt_tokens=22 if depth == 0 else 8190,
                       decode=decode, ttft=ttft)

    sweep = measure_at_depths(_Recorder(respond), "m", [0, 8192],
                              cfg=_cfg(repeat=3))

    # the repetitions sit inside a depth; the sweep is not run three times
    assert seen == [0, 0, 0, 8192, 8192, 8192]
    assert [pt.decode_tps for pt in sweep.points] == [95.1, 83.3]   # best kept
    assert [pt.ttft_s for pt in sweep.points] == [0.20, 0.50]       # median TTFT


# =====================================================================
# PERF-14: a depth the model cannot hold
# =====================================================================
def test_a_context_overflow_skips_only_that_depth():
    notes = []

    def respond(i, prompt):
        if _depth_of(prompt) == 32768:
            raise ProviderError("llamacpp generate failed for 'm': the request "
                                "exceeds the available context size")
        return _result(prompt_tokens=22, decode=95.1)

    sweep = measure_at_depths(_Recorder(respond), "m", [0, 32768, 0],
                              cfg=_cfg(), warn=notes.append)

    assert [pt.depth_requested for pt in sweep.points] == [0, 32768, 0]
    assert "exceeds the available context size" in sweep.points[1].skipped
    assert sweep.points[1].decode_tps == 0.0
    # the depths either side of it still measured
    assert sweep.points[0].decode_tps == 95.1
    assert sweep.points[2].decode_tps == 95.1
    assert [n for n in notes if "32768" in n]


def test_a_generation_timeout_skips_only_that_depth():
    notes = []

    def respond(i, prompt):
        if _depth_of(prompt) == 32768:
            raise ProviderError("llamacpp generate failed for 'm': timed out")
        return _result(prompt_tokens=22, decode=95.1)

    sweep = measure_at_depths(_Recorder(respond), "m", [0, 32768, 8192],
                              cfg=_cfg(), warn=notes.append)

    assert [pt.depth_requested for pt in sweep.points] == [0, 32768, 8192]
    assert sweep.points[0].decode_tps == 95.1
    assert "timed out" in sweep.points[1].skipped
    assert sweep.points[2].decode_tps == 95.1
    assert sweep.speed is not None
    assert sweep.speed.tokens_per_sec == 95.1
    assert [n for n in notes if "32768" in n]


def test_device_loss_preserves_completed_depths_and_stops_the_sweep():
    seen = []

    def respond(i, prompt):
        depth = _depth_of(prompt)
        seen.append(depth)
        if depth == 32768:
            raise ProviderError("decode failed: vk::Queue::submit: ErrorDeviceLost")
        return _result(prompt_tokens=22, decode=95.1)

    sweep = measure_at_depths(_Recorder(respond), "m", [0, 8192, 32768, 0],
                              cfg=_cfg())

    assert seen == [0, 8192, 32768]
    assert [pt.depth_requested for pt in sweep.points] == [0, 8192, 32768]
    assert sweep.points[0].decode_tps == 95.1
    assert sweep.points[1].decode_tps == 95.1
    assert "ErrorDeviceLost" in sweep.points[2].skipped
    assert sweep.speed is not None


def test_any_other_provider_error_propagates():
    def respond(i, prompt):
        raise ProviderError("connection refused: router restarting")

    with pytest.raises(ProviderError) as exc:
        measure_at_depths(_Recorder(respond), "m", [0, 8192], cfg=_cfg())

    assert "connection refused: router restarting" in str(exc.value)


def test_a_cache_hit_warns_without_discarding_the_measurement():
    notes = []
    rec = _Recorder(lambda i, p: _result(prompt_tokens=8190, decode=83.3,
                                         prefill=2540.0, cache_n=8180))

    pt = measure_at_depths(rec, "m", [8192], cfg=_cfg(),
                           warn=notes.append).points[0]

    assert pt.cache_hit_tokens == 8180
    assert pt.decode_tps == 83.3            # kept, not thrown away
    assert pt.prefill_tps == 2540.0
    assert pt.skipped is None
    assert len(notes) == 1
    assert "cache" in notes[0].lower() and "8192" in notes[0]


# =====================================================================
# PERF-15: which point feeds ModelReport.speed
# =====================================================================
def test_the_shallowest_measured_depth_becomes_the_reported_speed():
    def respond(i, prompt):
        depth = _depth_of(prompt)
        if depth == 32768:
            raise ProviderError("the request exceeds the available context size")
        return _result(prompt_tokens=22 if depth == 0 else 8190,
                       decode=95.1 if depth == 0 else 83.3)

    sweep = measure_at_depths(_Recorder(respond), "m", [32768, 8192, 0], cfg=_cfg())

    assert sweep.points[0].skipped is not None      # 32768 never measured
    assert sweep.speed is not None
    assert sweep.speed.tokens_per_sec == 95.1       # depth 0, asked last
