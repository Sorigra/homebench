"""Headless llama.cpp router lifecycle module.

Depends only on ``httpx`` and ``providers.base.ProviderError`` (the repo's
shared error type). It never imports ``providers``, ``tui``, ``runner``,
``rich`` or ``textual`` -- the CLI and the provider use this module, never the
other way around.
"""

from __future__ import annotations

from .models import (
    LifecycleOutcome,
    LifecyclePlan,
    LoadParams,
    ModelState,
    RouterInfo,
)

__all__ = [
    "LifecycleOutcome",
    "LifecyclePlan",
    "LoadParams",
    "ModelState",
    "RouterInfo",
]
