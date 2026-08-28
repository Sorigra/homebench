"""Context-depth measurement.

Single-stream tok/s is normally measured on a near-empty prompt, which is the
one context nobody actually works in: the same model loses roughly a quarter
of its decode rate and a third of its prefill rate by 32k tokens. This module
sweeps a model across several prompt depths in one run so the degradation is
visible instead of implied.

Nothing here talks to a backend directly -- the provider and the tokenizer are
injected -- so the sweep stays testable without a network.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from ..models import DepthMetrics, SpeedMetrics
from ..providers.base import Provider, ProviderError

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runner cycle
    from ..runner import RunConfig


def parse_depths(spec: str) -> List[int]:
    """Parse a depth spec like '0,8192,32768' into a list of prompt depths.

    Unlike :func:`~homebench.metrics.throughput.parse_levels` this keeps the
    order the user gave and does not deduplicate: the sweep measures exactly
    what was asked for, in that order. An empty spec means depth 0, the
    behaviour homebench had before the sweep existed.

    Raises ``ValueError`` naming the offending value for anything that is not
    a non-negative integer.
    """
    depths: List[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            raise ValueError(f"invalid context depth {part!r}")
        if value < 0:
            raise ValueError(f"invalid context depth {part!r}: must not be negative")
        depths.append(value)
    return depths or [0]


# The filler unit the depth prompts are built from. Measured against the live
# router: one repetition is 11 tokens, one hundred are 1001 -- 10 tokens per
# unit plus a single BOS token that must not be multiplied by the repeat
# count. ``_PAD_WORD`` is the fine adjustment, roughly one token each.
_FILLER_UNIT = "The quick brown fox jumps over the lazy dog. "
_FILLER_WORDS = 9
_PAD_WORD = "dog "
#: second calibration point; far enough from 1 that the BOS offset separates
#: cleanly from the per-unit slope
_PROBE_UNITS = 100
#: cap on the fine-adjustment round trips, so a hostile tokenizer cannot turn
#: prompt building into an unbounded loop
_MAX_REFINEMENTS = 8
#: fallback ratio when no tokenizer is available. The depth that actually gets
#: recorded comes from the server's ``prompt_n`` afterwards, so this only has
#: to be in the right neighbourhood.
_WORDS_PER_TOKEN = 0.75


def build_context_prompt(
    target: int,
    tokenize: Optional[Callable[[str], Optional[int]]] = None,
    *,
    base_prompt: str,
) -> Tuple[str, Optional[int]]:
    """Synthesise a prompt roughly ``target`` tokens deep.

    Returns the prompt text and its token count. The count is ``None`` when no
    tokenizer was available, which means the text is an estimate -- never a
    guess dressed up as a measurement.

    ``target <= 0`` is the shallow case and returns ``base_prompt`` untouched:
    depth 0 measures the model on the plain speed prompt, not on filler.

    ``base_prompt`` is passed in rather than imported so this module stays
    free of any dependency on the runner, and ``tokenize`` is injected so the
    module never opens a connection of its own.
    """
    if target <= 0:
        return base_prompt, None

    def synth(units: int, pads: int) -> str:
        return _FILLER_UNIT * units + _PAD_WORD * pads + "\n\n" + base_prompt

    if tokenize is not None:
        fitted = _fit_to_target(target, tokenize, synth)
        if fitted is not None:
            return fitted

    words = max(_FILLER_WORDS, int(round(target * _WORDS_PER_TOKEN)))
    return synth(max(1, words // _FILLER_WORDS), 0), None


def _fit_to_target(target, tokenize, synth) -> Optional[Tuple[str, int]]:
    """Fit the synthetic prompt to ``target`` tokens, or ``None`` if it can't.

    Two probes give the per-unit slope and the constant overhead (BOS plus the
    instruction, counted once). Solving those for the repeat count lands just
    under the target; pad words then walk up to it. Undershooting on purpose
    matters: an overshoot cannot be taken back without another round trip.
    """
    one = tokenize(synth(1, 0))
    many = tokenize(synth(_PROBE_UNITS, 0))
    if one is None or many is None:
        return None
    per_unit = (many - one) / (_PROBE_UNITS - 1)
    if per_unit <= 0:
        return None
    overhead = one - per_unit
    per_pad = per_unit / _FILLER_WORDS

    units = max(0, int((target - overhead) // per_unit) - 1)
    pads = 0
    text = synth(units, pads)
    count = tokenize(text)
    if count is None:
        return None

    for _ in range(_MAX_REFINEMENTS):
        if count >= target:
            break
        pads += max(1, int((target - count) // per_pad))
        candidate = synth(units, pads)
        grown = tokenize(candidate)
        if grown is None or grown <= count:
            break        # the tokenizer stopped responding to padding
        text, count = candidate, grown
    return text, count


#: A refusal that means "this prompt does not fit this model" and nothing
#: else. Matching is deliberately narrow: anything we cannot positively
#: recognise as a context overflow is re-raised, so a router that went away
#: mid-sweep still fails the model instead of being logged as a skipped depth.
_OVERFLOW_HINTS = (
    "context size",
    "context length",
    "context window",
    "n_ctx",
    "prompt is too long",
    "too many tokens",
)


def _is_context_overflow(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in _OVERFLOW_HINTS)


# SPEC_DEVIATION: design.md types measure_at_depths as -> List[DepthMetrics].
# Reason: the runner also needs the full SpeedMetrics of the shallowest depth
# for ModelReport.speed, and DepthMetrics cannot carry it back (it has no
# content_tokens / reasoning_tokens / timings_source). Returning both in one
# small value beats a second measurement pass or a lossy reconstruction.
@dataclass
class DepthSweep:
    """Everything one model's depth sweep produced.

    ``points`` is one entry per requested depth, in the order asked for.
    ``speed`` is the full timing of the shallowest depth that was actually
    measured -- it is what ``ModelReport.speed`` keeps, so ``score.py``,
    ``history`` and ``diff`` go on reading a single comparable number
    (PERF-15). ``None`` when every depth was skipped.
    """

    points: List[DepthMetrics] = field(default_factory=list)
    speed: Optional[SpeedMetrics] = None


def _tokenizer_for(provider: Provider, model: str) -> Optional[Callable[[str], Optional[int]]]:
    """Bind the provider's optional tokenizer to one model, or ``None``."""
    tokenize = getattr(provider, "tokenize", None)
    if tokenize is None:
        return None
    return lambda text: tokenize(model, text)


def measure_at_depths(
    provider: Provider,
    model: str,
    depths: List[int],
    *,
    cfg: "RunConfig",
    warn: Optional[Callable[[str], None]] = None,
) -> DepthSweep:
    """Measure ``model`` once at every depth in ``depths``, in that order.

    Every generation is sent with ``cache_prompt=False``: a repeated prompt
    served from a reused KV cache reports a prefill rate that is really a
    cache read (PERF-13). ``cfg.repeat`` repeats *within* a depth and the
    fastest run is kept, so the sweep itself runs once.

    A depth the model cannot hold is skipped with its reason recorded, and the
    remaining depths still run (PERF-14). Any other ``ProviderError`` is
    re-raised: it fails this model and only this model, the way the runner
    already isolates a backend that went away (MLC-11).
    """
    sweep = DepthSweep()
    tokenize = _tokenizer_for(provider, model)
    measured: List[Tuple[int, SpeedMetrics]] = []

    for depth in depths:
        prompt, _count = build_context_prompt(depth, tokenize,
                                              base_prompt=cfg.speed_prompt)
        try:
            runs = [
                provider.generate(
                    model,
                    prompt,
                    max_tokens=cfg.speed_max_tokens,
                    temperature=cfg.temperature,
                    seed=cfg.seed,
                    timeout=cfg.timeout,
                    cache_prompt=False,
                )
                for _ in range(max(1, cfg.repeat))
            ]
        except ProviderError as exc:
            if not _is_context_overflow(str(exc)):
                raise
            sweep.points.append(DepthMetrics(depth_requested=depth, skipped=str(exc)))
            _note(warn, f"{model}: depth {depth} skipped: {exc}")
            continue

        # Keep the fastest run as the representative sample and report the
        # median TTFT, which smooths out first-call noise.
        best = max(runs, key=lambda gen: gen.speed.tokens_per_sec)
        best.speed.ttft_s = statistics.median(gen.speed.ttft_s for gen in runs)
        sweep.points.append(DepthMetrics(
            depth_requested=depth,
            depth_actual=best.speed.prompt_tokens,
            prefill_tps=best.speed.prefill_tps,
            decode_tps=best.speed.tokens_per_sec,
            ttft_s=best.speed.ttft_s,
            prompt_eval_s=best.speed.prompt_eval_s,
            output_tokens=best.speed.output_tokens,
            cache_hit_tokens=best.cache_hit_tokens,
        ))
        measured.append((depth, best.speed))
        if best.cache_hit_tokens > 0:
            _note(warn, f"{model}: depth {depth} prefill may be contaminated by a "
                        f"reused KV cache ({best.cache_hit_tokens} prompt tokens "
                        f"served from cache)")

    if measured:
        sweep.speed = min(measured, key=lambda item: item[0])[1]
    return sweep


def _note(warn: Optional[Callable[[str], None]], message: str) -> None:
    if warn is not None:
        warn(message)
