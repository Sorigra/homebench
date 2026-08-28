"""Resolve the load parameters for a model by declared precedence.

Headless: no imports from ``providers``, ``tui``, ``runner`` or ``rich``.
``default_home`` is copied from ``history.py`` because importing that module
would pull in ``rich`` (AD-005).
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any, Dict, List, Optional

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
