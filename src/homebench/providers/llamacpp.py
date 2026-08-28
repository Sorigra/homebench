"""llama.cpp server provider (``llama-server`` from llama.cpp).

Uses the OpenAI-compatible ``/v1`` endpoints. ``llama-server`` typically
serves a single loaded model; discovery returns whatever ``/v1/models``
reports. Memory is left to RSS sampling.

When the host is llama.cpp in **router** mode it also owns model lifecycle
over HTTP, so ``unload()`` really evicts the model instead of being the
inherited no-op. Router capability is probed per instance, never cached
globally: the two hosts of a machine can run different builds (AD-004).
"""

from __future__ import annotations

from typing import Optional

from .openai_compat import OpenAICompatibleProvider


class LlamaCppProvider(OpenAICompatibleProvider):
    name = "llamacpp"
    default_host = "http://localhost:8080"
    host_env = "LLAMACPP_HOST"
    api_key_env = "LLAMACPP_API_KEY"
    _process_hint = "llama-server"

    def __init__(self, host: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(host=host, api_key=api_key)
        self._router = None            # resolved lazily, for this host only
        self._router_probed = False
        #: last best-effort unload failure, kept so a run can report it
        self.last_unload_error: Optional[str] = None

    # ------------------------------------------------------------------
    def router(self):
        """The router client for this host, or ``None`` if it is not a router.

        Probed once per instance. A fresh instance re-probes, so a second host
        is never judged by the first host's answer (AD-004).
        """
        if not self._router_probed:
            from ..lifecycle.router import LlamaRouterClient

            self._router_probed = True
            client = LlamaRouterClient(host=self.host, api_key=self.api_key)
            self._router = client if client.is_router() else None
        return self._router

    def unload(self, model: str) -> None:
        """Evict ``model`` on a router host; a no-op anywhere else.

        Best-effort, like the other providers: a failure is recorded in
        ``last_unload_error`` and never interrupts the run (MLC-14).
        """
        from .base import ProviderError

        client = self.router()
        if client is None:
            return None
        try:
            client.unload(model)
        except ProviderError as exc:
            self.last_unload_error = str(exc)
            return None
        self.last_unload_error = None
        return None
