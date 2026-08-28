"""HTTP client for the llama.cpp router protocol.

No decision logic lives here: this class only speaks the wire protocol and
raises :class:`ProviderError` on failure.

``normalize_host`` is copied from ``providers/openai_compat.py`` on purpose:
the lifecycle package must not import ``providers`` (AD-005), and copying a
tiny host-normaliser is the same pattern ``providers/ollama.py`` already uses.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from ..providers.base import ProviderError
from .models import ModelState, RouterInfo

_PROPS_TIMEOUT = 10.0
_LIST_TIMEOUT = 10.0


def normalize_host(host: str, default: str) -> str:
    host = (host or "").strip().rstrip("/")
    if not host:
        host = default
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


class LlamaRouterClient:
    """Talks the llama.cpp router HTTP protocol for one host."""

    default_host = "http://localhost:8080"
    host_env = "LLAMACPP_HOST"
    api_key_env = "LLAMACPP_API_KEY"

    def __init__(self, host: Optional[str] = None, api_key: Optional[str] = None):
        env_host = os.environ.get(self.host_env) if self.host_env else None
        self.host = normalize_host(host or env_host or "", self.default_host)
        env_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        self.api_key = api_key or env_key

    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _auth_error(self) -> ProviderError:
        # never echo the key value
        return ProviderError(f"Router authentication rejected at {self.host}")

    def _unreachable(self, exc: Exception) -> ProviderError:
        return ProviderError(f"Could not reach llama.cpp router at {self.host}: {exc}")

    def _get_json(self, path: str, timeout: float) -> Any:
        try:
            r = httpx.get(f"{self.host}{path}", headers=self._headers(), timeout=timeout)
        except httpx.HTTPError as exc:
            raise self._unreachable(exc)
        if r.status_code in (401, 403):
            raise self._auth_error()
        try:
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Router at {self.host} returned an error: {exc}")
        try:
            return r.json()
        except ValueError:
            raise ProviderError(f"Router at {self.host} returned invalid JSON for {path}")

    # ------------------------------------------------------------------
    def props(self) -> RouterInfo:
        """``GET /props``. Raises ProviderError on auth failure or unreachable host."""
        data = self._get_json("/props", _PROPS_TIMEOUT)
        if not isinstance(data, dict):
            raise ProviderError(f"Router at {self.host} returned an unexpected /props payload")
        return RouterInfo.from_dict(data)

    def is_router(self) -> bool:
        """True only when ``GET /props`` reports ``role == "router"``.

        Any failure (404, missing field, invalid JSON, network error, auth) is
        treated as "not a router" -- the detection is positive by design (AD-004).
        """
        try:
            return self.props().role == "router"
        except ProviderError:
            return False

    # ------------------------------------------------------------------
    def list_models(self) -> List[ModelState]:
        """``GET /v1/models`` -> resolved state and argv for every model.

        The router reports ``status.args`` (resolved argv) even for models that
        are ``unloaded``, so that field is populated regardless of state.
        """
        data = self._get_json("/v1/models", _LIST_TIMEOUT)
        entries = data.get("data", []) if isinstance(data, dict) else []
        return [
            ModelState.from_dict(m)
            for m in entries
            if isinstance(m, dict) and m.get("id")
        ]

    def loaded_models(self) -> List[ModelState]:
        """Just the models currently ``loaded``."""
        return [m for m in self.list_models() if m.status == "loaded"]
