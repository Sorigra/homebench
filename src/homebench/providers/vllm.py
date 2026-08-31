"""vLLM provider.

vLLM's OpenAI-compatible server (``vllm serve``) listens on port 8000 by
default. If the server was started with ``--api-key``, set ``VLLM_API_KEY``
(or ``OPENAI_API_KEY``) and it will be sent as a bearer token.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

import httpx

from .base import GenerationResult, TokenCallback
from .openai_compat import OpenAICompatibleProvider


_METRICS = {
    "requests": "vllm:request_prefill_time_seconds_count",
    "prefill_s": "vllm:request_prefill_time_seconds_sum",
    "decode_s": "vllm:request_decode_time_seconds_sum",
    "prefill_tokens": "vllm:request_prefill_kv_computed_tokens_sum",
    "generation_tokens": "vllm:request_generation_tokens_sum",
}


class VLLMProvider(OpenAICompatibleProvider):
    name = "vllm"
    default_host = "http://localhost:8000"
    host_env = "VLLM_HOST"
    api_key_env = "VLLM_API_KEY"
    _process_hint = "vllm"

    def __init__(self, host: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(host=host, api_key=api_key)
        # Fall back to the conventional OpenAI key if a vLLM-specific one isn't set.
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")

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
        # Speed probes pass cache_prompt=False. Limit the two extra metrics
        # requests to those probes so quality runs keep their existing cost.
        before = self._metrics_snapshot(model) if not cache_prompt else None
        result = super().generate(
            model, prompt, max_tokens=max_tokens, temperature=temperature,
            seed=seed, on_token=on_token, timeout=timeout,
            cache_prompt=cache_prompt,
        )
        if before is not None:
            after = self._metrics_snapshot(model)
            if after is not None:
                self._apply_metrics_delta(result, before, after)
        return result

    def _metrics_snapshot(self, model: str) -> Optional[Dict[str, float]]:
        try:
            response = httpx.get(f"{self.host}/metrics", headers=self._headers(),
                                 timeout=2.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        marker = f'model_name="{_escape_label(model)}"'
        values: Dict[str, float] = {}
        try:
            for line in response.text.splitlines():
                if not line or line.startswith("#") or marker not in line:
                    continue
                sample, raw_value = line.rsplit(None, 1)
                for key, metric in _METRICS.items():
                    if sample.startswith(metric + "{"):
                        values[key] = values.get(key, 0.0) + float(raw_value)
                        break
        except (ValueError, OverflowError):
            return None
        return values if values.keys() >= _METRICS.keys() else None

    @staticmethod
    def _apply_metrics_delta(result: GenerationResult, before: Dict[str, float],
                             after: Dict[str, float]) -> None:
        delta = {key: after[key] - before[key] for key in _METRICS}
        # Prometheus data is process-wide. More than one completed request
        # means another client overlapped this measurement, so keep the clean
        # client-side fallback rather than attributing its work to this run.
        if delta["requests"] != 1:
            return
        decode_tokens = delta["generation_tokens"] - 1  # first token is prefill
        if (delta["prefill_tokens"] <= 0 or delta["prefill_s"] <= 0 or
                decode_tokens <= 0 or delta["decode_s"] <= 0):
            return
        speed = result.speed
        speed.prompt_eval_s = delta["prefill_s"]
        speed.prefill_tps = delta["prefill_tokens"] / delta["prefill_s"]
        speed.eval_s = delta["decode_s"]
        speed.tokens_per_sec = decode_tokens / delta["decode_s"]
        speed.timings_source = "server"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
