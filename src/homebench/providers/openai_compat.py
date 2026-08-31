"""Generic OpenAI-compatible provider.

Most local runners (LM Studio, llama.cpp's ``llama-server``, vLLM, Jan,
LocalAI, text-generation-webui, …) expose an OpenAI-compatible HTTP API:
``GET /v1/models`` for discovery and ``POST /v1/chat/completions`` for
generation. This base implements both; concrete providers just set the
default host / env var / process hint (and can enrich metadata).

Timings (tok/s, TTFT) are measured client-side from the streamed response,
since the OpenAI-compatible API doesn't report server-side eval durations.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

import httpx

from ..models import MemoryMetrics, ModelInfo, SpeedMetrics
from .base import GenerationResult, Provider, ProviderError, TokenCallback


def normalize_host(host: str, default: str) -> str:
    host = (host or "").strip().rstrip("/")
    if not host:
        host = default
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


class OpenAICompatibleProvider(Provider):
    """Talks to any server implementing the OpenAI ``/v1`` chat API."""

    name = "openai"
    default_host = "http://localhost:8000"
    host_env: Optional[str] = "OPENAI_BASE_URL"
    api_key_env: Optional[str] = "OPENAI_API_KEY"
    _process_hint: Optional[str] = None

    def __init__(self, host: Optional[str] = None, api_key: Optional[str] = None):
        env_host = os.environ.get(self.host_env) if self.host_env else None
        self.host = normalize_host(host or env_host or "", self.default_host)
        env_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        self.api_key = api_key or env_key

    @property
    def process_hint(self) -> str:
        return self._process_hint or self.name

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.host}/v1/models", headers=self._headers(), timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> List[ModelInfo]:
        try:
            r = httpx.get(f"{self.host}/v1/models", headers=self._headers(), timeout=10.0)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach {self.name} at {self.host}: {exc}")
        models = [
            ModelInfo(name=m.get("id", ""), provider=self.name)
            for m in r.json().get("data", [])
            if m.get("id")
        ]
        models.sort(key=lambda x: x.name)
        return models

    # ------------------------------------------------------------------
    def generate(
        self,
        model: str,
        prompt: str,
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        seed: Optional[int] = None,
        on_token: TokenCallback = None,
        timeout: float = 300.0,
        cache_prompt: bool = True,
    ) -> GenerationResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream_options": {"include_usage": True},
        }
        if seed is not None:
            payload["seed"] = seed
        if not cache_prompt:
            # llama.cpp honours this; servers that don't just ignore it
            payload["cache_prompt"] = False

        speed = SpeedMetrics()
        chunks: List[str] = []
        content_deltas = 0
        reasoning_deltas = 0
        start = time.perf_counter()
        first_token_at: Optional[float] = None
        usage = None
        timings = None

        try:
            with httpx.stream(
                "POST", f"{self.host}/v1/chat/completions",
                json=payload, headers=self._headers(), timeout=timeout,
            ) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    # Streaming responses do not expose their body until it is
                    # consumed.  Keep llama.cpp's useful error text before the
                    # status exception leaves this context manager.
                    resp.read()
                    raise
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    # An in-stream failure arrives as an error object on a 200
                    # response. Left unread it looks like a generation that
                    # simply produced nothing -- the same 0.00 tok/s that
                    # reads as a real result (PERF-05).
                    if isinstance(obj, dict) and obj.get("error"):
                        raise ProviderError(
                            f"{self.name} generate failed for {model!r}: "
                            f"{_stream_error(obj['error'])}"
                        )
                    if obj.get("usage"):
                        usage = obj["usage"]
                    # llama.cpp ships its own timings alongside usage; they
                    # are measured server-side, free of network and parsing
                    # noise, so they win over the client stopwatch (PERF-06)
                    if obj.get("timings"):
                        timings = obj["timings"]
                    for choice in obj.get("choices", []):
                        delta = choice.get("delta") or {}
                        piece = delta.get("content") or ""
                        # Reasoning extensions use either reasoning_content
                        # (llama.cpp and older vLLM) or reasoning (vLLM 0.28).
                        # They cost the same compute, so count both as output.
                        thought = (delta.get("reasoning_content") or
                                   delta.get("reasoning") or "")
                        if (piece or thought) and first_token_at is None:
                            first_token_at = time.perf_counter()
                        if piece:
                            chunks.append(piece)
                            content_deltas += 1
                            if on_token is not None:
                                on_token(piece)
                        if thought:
                            reasoning_deltas += 1
        except httpx.HTTPStatusError as exc:
            detail = _http_error_detail(exc.response)
            suffix = f": {detail}" if detail else ""
            raise ProviderError(
                f"{self.name} generate failed for {model!r}: {exc}{suffix}"
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} generate failed for {model!r}: {exc}")

        end = time.perf_counter()
        speed.total_s = end - start
        # usage doesn't split the two kinds, so the split is delta-counted
        # (best-effort: ~1 token per delta), same as the no-usage fallback
        speed.content_tokens = content_deltas
        speed.reasoning_tokens = reasoning_deltas
        if usage:
            speed.prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            speed.output_tokens = int(usage.get("completion_tokens", 0) or 0)
        else:
            speed.output_tokens = content_deltas + reasoning_deltas
        if first_token_at is not None:
            speed.ttft_s = first_token_at - start
            speed.eval_s = max(0.0, end - first_token_at)
            if speed.eval_s > 0 and speed.output_tokens > 0:
                speed.tokens_per_sec = speed.output_tokens / speed.eval_s

        cache_hit_tokens = 0
        if timings:
            speed.timings_source = "server"
            speed.prompt_eval_s = float(timings.get("prompt_ms") or 0.0) / 1000.0
            # 0 is not a plausible rate: read it as "the server didn't say"
            prefill = timings.get("prompt_per_second")
            speed.prefill_tps = float(prefill) if prefill else None
            decode = timings.get("predicted_per_second")
            if decode:
                speed.tokens_per_sec = float(decode)
            prompt_n = timings.get("prompt_n")
            if prompt_n is not None:
                speed.prompt_tokens = int(prompt_n)
            cache_hit_tokens = int(timings.get("cache_n") or 0)

        return GenerationResult(text="".join(chunks), speed=speed,
                                cache_hit_tokens=cache_hit_tokens)

    # ------------------------------------------------------------------
    def memory(self, model: str) -> MemoryMetrics:
        # OpenAI-compatible servers don't expose memory; rely on RSS sampling.
        return MemoryMetrics()


def _stream_error(err) -> str:
    """Human-readable text of an error object streamed inside a 200 response."""
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err)


def _http_error_detail(response: httpx.Response) -> str:
    """Keep a server's useful error message when the status is non-2xx."""
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return response.text.strip()
    if isinstance(body, dict) and "error" in body:
        return _stream_error(body["error"])
    return str(body)
