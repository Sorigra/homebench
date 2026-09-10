"""HTTP client for the llama.cpp router protocol.

No decision logic lives here: this class only speaks the wire protocol and
raises :class:`ProviderError` on failure.

``normalize_host`` is copied from ``providers/openai_compat.py`` on purpose:
the lifecycle package must not import ``providers`` (AD-005), and copying a
tiny host-normaliser is the same pattern ``providers/ollama.py`` already uses.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

from ..providers.base import ProviderError
from .models import ModelState, RouterInfo

_PROPS_TIMEOUT = 10.0
_LIST_TIMEOUT = 10.0
_MUTATION_TIMEOUT = 60.0
_LOAD_TIMEOUT = 300.0   # TD-06: aligned with RunConfig.timeout
_CAPACITY_TIMEOUT = 60.0
_POLL_INTERVAL = 1.0


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

    # ------------------------------------------------------------------
    def load(self, model: str, extra_args: Optional[List[str]] = None) -> None:
        """``POST /models/load``. ``extra_args`` is included only when non-empty."""
        payload: Dict[str, Any] = {"model": model}
        if extra_args:
            payload["extra_args"] = list(extra_args)
        self._post_mutation("/models/load", payload, model)

    def unload(self, model: str) -> None:
        """``POST /models/unload``."""
        self._post_mutation("/models/unload", {"model": model}, model)

    def _post_mutation(self, path: str, payload: Dict[str, Any], model: str) -> None:
        try:
            r = httpx.post(
                f"{self.host}{path}",
                json=payload,
                headers=self._headers(),
                timeout=_MUTATION_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise self._unreachable(exc)
        if r.status_code in (401, 403):
            raise self._auth_error()
        if r.status_code == 404:
            # The route exists on this build; a 404 here means the model *file*
            # is missing, not that the endpoint is absent (AD-001 correction).
            raise ProviderError(
                f"Model file not found for {model!r} on router at {self.host}"
            )
        if r.status_code >= 400:
            # propagate the router's own message unchanged (MLC-13)
            raise ProviderError(
                f"Router rejected {path} for {model!r}: {_router_message(r)}"
            )

    # ------------------------------------------------------------------
    def wait_until_loaded(
        self,
        model: str,
        timeout: float = _LOAD_TIMEOUT,
        *,
        now=time.monotonic,
        sleep=time.sleep,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        """Poll ``GET /v1/models`` until ``model`` is ``loaded``.

        Raises :class:`ProviderError` if ``timeout`` seconds pass first (default
        300 s, TD-06). ``now`` and ``sleep`` are injectable so the timeout test
        does not really wait.
        """
        deadline = now() + timeout
        while True:
            state = next((m for m in self.list_models() if m.id == model), None)
            if state is not None and state.status == "loaded":
                return
            if now() >= deadline:
                raise ProviderError(
                    f"Timed out after {timeout:.0f}s waiting for {model!r} "
                    f"to load on router at {self.host}"
                )
            sleep(poll_interval)


    def wait_until_unloaded(
        self,
        models: List[str],
        timeout: float = _CAPACITY_TIMEOUT,
        *,
        now=time.monotonic,
        sleep=time.sleep,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        """Poll ``GET /v1/models`` until none of ``models`` is still ``loaded``.

        ``POST /models/unload`` is accepted before the instance has actually
        stopped, so reloading the *same* model straight after unloading it is
        refused with "model is already running". Waiting for a free slot is not
        enough to catch that: the slot is free (the count already dropped) while
        that particular instance is still shutting down.
        """
        wanted = [m for m in (models or []) if m]
        if not wanted:
            return
        deadline = now() + timeout
        while True:
            status = {m.id: m.status for m in self.list_models()}
            still = [m for m in wanted if status.get(m) == "loaded"]
            if not still:
                return
            if now() >= deadline:
                raise ProviderError(
                    f"Timed out after {timeout:.0f}s waiting for "
                    f"{', '.join(still)} to unload on router at {self.host}"
                )
            sleep(poll_interval)

    def wait_for_capacity(
        self,
        timeout: float = _CAPACITY_TIMEOUT,
        *,
        now=time.monotonic,
        sleep=time.sleep,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        """Poll ``GET /v1/models`` until fewer models are loaded than ``--models-max``.

        ``POST /models/unload`` answers before the instance slot is actually
        released, so a load issued right after an unload can still come back
        "model limit reached, try again later". Callers that have just unloaded
        wait here first rather than racing the router.

        A no-op when ``GET /props`` does not report ``max_instances`` -- an
        older build, or a props call that fails: there is no known capacity to
        wait for, so the load is attempted and the router's own error stands.
        """
        try:
            max_instances = self.props().max_instances or 0
        except ProviderError:
            return
        if max_instances <= 0:
            return
        deadline = now() + timeout
        while True:
            in_use = len(self.loaded_models())
            if in_use < max_instances:
                return
            if now() >= deadline:
                raise ProviderError(
                    f"Timed out after {timeout:.0f}s waiting for a free model slot "
                    f"on router at {self.host} ({in_use} of {max_instances} in use)"
                )
            sleep(poll_interval)


def _router_message(r: httpx.Response) -> str:
    """The router's own error message, unmodified, for propagation (MLC-13)."""
    try:
        body = r.json()
    except ValueError:
        return r.text.strip() or "HTTP {}".format(r.status_code)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err
        if body.get("message"):
            return str(body["message"])
    return r.text.strip() or "HTTP {}".format(r.status_code)
