"""Resolve the load parameters for a model by declared precedence.

Headless: no imports from ``providers``, ``tui``, ``runner`` or ``rich``.
``default_home`` is copied from ``history.py`` because importing that module
would pull in ``rich`` (AD-005).
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any, Dict, List, NamedTuple, Optional

from .models import LoadParams, ModelState

_OVERRIDE_FILENAME = "load-params.json"

#: ``-ngl`` value meaning "offload every layer" (llama.cpp treats any large
#: number this way).
NGL_ALL = 999

#: Headroom multiplier over raw weight bytes for the KV cache and runtime.
_MEM_HEADROOM = 1.15


def default_home() -> str:
    """``$HOMEBENCH_HOME`` or ``~/.homebench`` (copied from history.py)."""
    return os.environ.get("HOMEBENCH_HOME") or os.path.expanduser("~/.homebench")


def _override_path(path: Optional[str]) -> str:
    if path:
        return path
    return os.path.join(default_home(), _OVERRIDE_FILENAME)


def load_overrides(path: Optional[str] = None) -> Dict[str, List[str]]:
    """Read the per-model load-param override file.

    Defaults to ``$HOMEBENCH_HOME/load-params.json`` (TD-07). A missing file
    returns ``{}``. A malformed file warns and returns ``{}`` -- it never
    raises, so a broken override file cannot abort a run (MLC-13, edge case).
    """
    resolved = _override_path(path)
    if not os.path.isfile(resolved):
        return {}
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError) as exc:
        warnings.warn(f"Ignoring malformed load-param override file {resolved}: {exc}")
        return {}
    if not isinstance(data, dict):
        warnings.warn(
            f"Ignoring load-param override file {resolved}: expected a JSON object"
        )
        return {}
    return data


def suggest_ngl(file_bytes: int, budget_bytes: int) -> int:
    """Suggest a ``-ngl`` value from the model file size and the memory budget.

    - budget of zero or less, or an unknown file size: ``0`` (CPU only).
    - model plus headroom fits the budget: :data:`NGL_ALL` (full offload).
    - model at least as large as the budget: ``0``.
    - in between: a proportional fraction of the layers.

    Always returns an integer ``>= 0`` (MLC-13, P2 AC5).
    """
    if budget_bytes <= 0 or file_bytes <= 0:
        return 0
    needed = file_bytes * _MEM_HEADROOM
    if needed <= budget_bytes:
        return NGL_ALL
    if file_bytes >= budget_bytes:
        return 0
    return max(0, int(NGL_ALL * (budget_bytes / needed)))


def resolve(
    model: ModelState,
    explicit: Optional[List[str]] = None,
    overrides: Optional[Dict[str, List[str]]] = None,
    hardware: Optional[Any] = None,
    file_bytes: int = 0,
) -> LoadParams:
    """Resolve a model's load parameters by declared precedence (AD-003).

    explicit flag > override JSON > server preset (``model.args``) >
    ``-ngl`` heuristic > llama.cpp default. ``LoadParams.origin`` records which
    source won, so two runs of the same model are distinguishable (MLC-09).

    ``file_bytes`` is needed for the heuristic tier; the design's ``resolve``
    sketch omits it because the heuristic was the last tier decided.
    """
    if explicit:
        return LoadParams(extra_args=list(explicit), origin="explicit")

    override_args = (overrides or {}).get(model.id)
    if override_args:
        return LoadParams(extra_args=list(override_args), origin="json")

    if model.args:
        return LoadParams(extra_args=list(model.args), origin="preset")

    if hardware is not None and file_bytes > 0:
        budget, _ = hardware.memory_budget()
        ngl = suggest_ngl(file_bytes, budget)
        return LoadParams(extra_args=["-ngl", str(ngl)], origin="heuristic")

    return LoadParams(extra_args=[], origin="default")


#: llama.cpp spellings of the two flags that decide how much context one
#: request may actually use. ``--ctx-size`` is the size of the *whole* KV
#: cache and ``--parallel`` is how many slots share it, so a request can only
#: ever be as deep as ``ctx-size / parallel``.
_CTX_FLAGS = ("--ctx-size", "-c", "--n-ctx")
_PARALLEL_FLAGS = ("--parallel", "-np")


class ContextBudget(NamedTuple):
    """How deep one request may go on a given server.

    ``limit`` is the per-slot context in tokens; ``source`` says where the
    number came from, so a skipped depth explains *why* rather than only that
    it was too deep.
    """

    limit: int
    source: str


def _flag_int(args: List[str], flags) -> Optional[int]:
    """Last value given for any spelling of ``flags``, as an int, or ``None``.

    The last occurrence wins, which is how llama.cpp itself resolves a flag
    repeated on one command line.
    """
    found: Optional[int] = None
    for i, token in enumerate(args or []):
        if token in flags and i + 1 < len(args):
            try:
                found = int(args[i + 1])
            except (TypeError, ValueError):
                continue
    return found


def usable_context(args: Optional[List[str]]) -> Optional[ContextBudget]:
    """Per-request context of a server started with ``args``, or ``None``.

    ``None`` means "not knowable from this argv" -- no ``--ctx-size``, or an
    explicit ``0``, which tells llama.cpp to take the context from the model
    file. Callers must treat that as "no limit known" and let the server
    decide, never as "no context".

    The division by ``--parallel`` is the whole point: a 32768-token cache
    split across two slots refuses a 20k-token prompt, and the error only
    ever names the 16384 the request actually had (PERF-14).

    This is an **upper bound**, not the truth: llama.cpp caps ``--ctx-size``
    at the model's trained context, so a preset asking for 133120 on a model
    trained to 131072 serves 131072 and says nothing. Prefer a server that
    can report its own context (``Provider.context_window``) and keep this
    for the servers that cannot.
    """
    ctx = _flag_int(args, _CTX_FLAGS)
    if not ctx or ctx <= 0:
        return None
    parallel = _flag_int(args, _PARALLEL_FLAGS) or 1
    parallel = max(1, parallel)
    source = f"--ctx-size {ctx}"
    if parallel > 1:
        source += f" / --parallel {parallel}"
    return ContextBudget(limit=ctx // parallel, source=source)
