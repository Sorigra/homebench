"""Resolve the load parameters for a model by declared precedence.

Headless: no imports from ``providers``, ``tui``, ``runner`` or ``rich``.
``default_home`` is copied from ``history.py`` because importing that module
would pull in ``rich`` (AD-005).
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Dict, List, Optional

_OVERRIDE_FILENAME = "load-params.json"


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
