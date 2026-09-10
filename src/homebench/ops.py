"""Headless snapshots for the guided-ops panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .lifecycle.router import LlamaRouterClient
from .providers.base import ProviderError


@dataclass
class RouterStatus:
    host: str
    reachable: bool
    build_info: Optional[str] = None
    resident_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None


def router_status(client: Optional[LlamaRouterClient] = None) -> RouterStatus:
    router = client or LlamaRouterClient()
    host = router.host
    try:
        info = router.props()
        residents = [m.id for m in router.loaded_models() if m.id]
        return RouterStatus(
            host=host,
            reachable=True,
            build_info=info.build_info or None,
            resident_ids=residents,
        )
    except ProviderError as exc:
        error = str(exc)
        if router.api_key and router.api_key in error:
            error = error.replace(router.api_key, "***")
        return RouterStatus(host=host, reachable=False, error=error)
