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

import os
import re
from typing import List, Optional

import httpx

from ..models import MemoryMetrics
from .openai_compat import OpenAICompatibleProvider

#: /tokenize is cheap, but a 32k prompt still has to cross the wire
_TOKENIZE_TIMEOUT = 30.0

#: Host directory the server's model directory is mounted from. Needed only
#: when the server runs in a container: its ``--model`` path is then a path
#: inside that container, which does not exist on this side of the mount.
MODEL_DIR_ENV = "HOMEBENCH_MODEL_DIR"

#: llama.cpp names a split model ``<stem>-00001-of-00003.gguf`` and the argv
#: carries only the first shard, so the footprint is the sum of the set.
_SHARD_RE = re.compile(r"^(?P<stem>.+)-\d{5}-of-(?P<total>\d{5})\.gguf$")


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

    def tokenize(self, model: str, text: str) -> Optional[int]:
        """Count ``text`` in tokens via ``POST /tokenize``, or ``None``.

        Every failure answers ``None``: the route is missing on some builds,
        and it returns 400 when the model is not resident. Neither is worth
        interrupting a measurement over.
        """
        try:
            r = httpx.post(
                f"{self.host}/tokenize",
                json={"model": model, "content": text},
                headers=self._headers(), timeout=_TOKENIZE_TIMEOUT,
            )
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        try:
            data = r.json()
        except ValueError:
            return None
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(tokens, list):
            return None
        return len(tokens)

    def memory(self, model: str) -> MemoryMetrics:
        """Footprint of ``model``, taken from the GGUF the router resolved.

        An OpenAI-compatible server says nothing about memory, and on a
        GPU-offloading host RSS sampling is blind: with ``--n-gpu-layers`` the
        weights live in GPU memory and never enter the server process's
        resident set, so a 38 GB model samples as ~2 GB. The router does
        publish the argv it resolved for each model, and the ``--model`` file
        it names is an exact number.

        Unresolvable (not a router, model unknown, file not reachable from
        here) answers an empty metric -- the column stays blank rather than
        showing a guess.
        """
        path = self._model_file(model)
        if path is None:
            return MemoryMetrics()
        try:
            return MemoryMetrics(size_bytes=_gguf_bytes(path))
        except OSError:
            return MemoryMetrics()

    def _model_file(self, model: str) -> Optional[str]:
        """Local path of the GGUF the router loads for ``model``, or ``None``."""
        from .base import ProviderError

        client = self.router()
        if client is None:
            return None
        try:
            states = client.list_models()
        except ProviderError:
            return None
        argv = next((s.args for s in states if s.id == model), None)
        if argv is None:
            return None
        return _resolve_model_path(_model_arg(argv))

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


# ----------------------------------------------------------------------
def _model_arg(argv: List[str]) -> Optional[str]:
    """The value of ``--model`` / ``-m`` in a resolved argv."""
    for flag, value in zip(argv, argv[1:]):
        if flag in ("--model", "-m"):
            return value
    return None


def _resolve_model_path(raw: Optional[str]) -> Optional[str]:
    """Map the server's ``--model`` path to a file readable from here.

    A plain ``llama-server`` names a real host path and resolves directly. A
    containerised one names a path inside the container (``/models/...``) and
    the mount point is not discoverable over HTTP, so the caller supplies the
    host side in ``$HOMEBENCH_MODEL_DIR`` and we drop leading components until
    the remainder resolves under it.
    """
    if not raw:
        return None
    if os.path.isfile(raw):
        return raw
    host_dir = os.environ.get(MODEL_DIR_ENV)
    if not host_dir:
        return None
    parts = [p for p in raw.split("/") if p]
    for i in range(len(parts)):
        candidate = os.path.join(host_dir, *parts[i:])
        if os.path.isfile(candidate):
            return candidate
    return None


def _gguf_bytes(path: str) -> int:
    """Size of ``path``, summing every shard when it is a split GGUF.

    An incomplete shard set reports only the shard we have rather than
    extrapolating a total that was never on disk.
    """
    match = _SHARD_RE.match(os.path.basename(path))
    if match is None:
        return os.path.getsize(path)
    total = int(match.group("total"))
    stem = match.group("stem")
    directory = os.path.dirname(path)
    shards = [
        os.path.join(directory, "%s-%05d-of-%05d.gguf" % (stem, n, total))
        for n in range(1, total + 1)
    ]
    if not all(os.path.isfile(s) for s in shards):
        return os.path.getsize(path)
    return sum(os.path.getsize(s) for s in shards)
