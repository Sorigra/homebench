import json

import pytest

from homebench.providers import (
    LlamaCppProvider,
    OpenAICompatibleProvider,
    ProviderError,
    VLLMProvider,
    available_providers,
    get_provider,
)
from homebench.providers.openai_compat import normalize_host


def test_all_providers_registered():
    for name in ("ollama", "lmstudio", "llamacpp", "vllm", "mlx", "openai"):
        assert name in available_providers()


def test_mlx_provider():
    from homebench.providers import MLXProvider, get_provider
    from homebench.providers import _AUTO_DETECT

    p = get_provider("mlx")
    assert isinstance(p, MLXProvider)
    assert p.host == "http://localhost:8080"
    assert p.process_hint == "mlx_lm.server"
    # explicit-only: not auto-detected (shares llama.cpp's port)
    assert "mlx" not in _AUTO_DETECT
    # unreachable is graceful
    assert MLXProvider(host="http://127.0.0.1:9").is_available() is False


def test_unknown_provider_raises():
    from homebench.providers import ProviderError

    with pytest.raises(ProviderError):
        get_provider("nope")


def test_normalize_host():
    assert normalize_host("localhost:8080", "http://d:1") == "http://localhost:8080"
    assert normalize_host("", "http://localhost:8080") == "http://localhost:8080"
    assert normalize_host("https://x:1/", "http://d:1") == "https://x:1"


@pytest.mark.parametrize(
    "cls,host,hint",
    [
        (LlamaCppProvider, "http://localhost:8080", "llama-server"),
        (VLLMProvider, "http://localhost:8000", "vllm"),
    ],
)
def test_provider_defaults(cls, host, hint):
    p = cls()
    assert p.host == host
    assert p.process_hint == hint


def test_host_env_override(monkeypatch):
    monkeypatch.setenv("LLAMACPP_HOST", "http://box:9999")
    assert LlamaCppProvider().host == "http://box:9999"


def test_api_key_header(monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "secret")
    p = VLLMProvider()
    assert p._headers() == {"Authorization": "Bearer secret"}
    assert OpenAICompatibleProvider()._headers() == {}


def test_unavailable_is_graceful():
    assert VLLMProvider(host="http://127.0.0.1:9").is_available() is False


class _FakeStream:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)


def test_streaming_generate_parses_content_and_usage(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}',
        "data: [DONE]",
    ]
    import homebench.providers.openai_compat as mod
    monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _FakeStream(lines))

    seen = []
    result = OpenAICompatibleProvider().generate(
        "m", "hi", on_token=seen.append
    )
    assert result.text == "Hello world"
    assert result.speed.prompt_tokens == 5
    assert result.speed.output_tokens == 2
    assert seen == ["Hello", " world"]


def test_streaming_generate_without_usage_counts_deltas(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"a"}}]}',
        'data: {"choices":[{"delta":{"content":"b"}}]}',
        'data: {"choices":[{"delta":{"content":"c"}}]}',
        "data: [DONE]",
    ]
    import homebench.providers.openai_compat as mod
    monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _FakeStream(lines))

    result = OpenAICompatibleProvider().generate("m", "hi")
    assert result.text == "abc"
    assert result.speed.output_tokens == 3  # fell back to delta count


# =====================================================================
# reasoning_content counts as generated output (PERF-01..PERF-04)
# =====================================================================
def _stream(monkeypatch, lines, clock=None):
    """Point generate() at a canned SSE stream; optionally script the clock."""
    import homebench.providers.openai_compat as mod
    monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _FakeStream(lines))
    if clock is not None:
        ticks = iter(clock)
        monkeypatch.setattr(mod.time, "perf_counter", lambda: next(ticks))


# a reasoning model: every token arrives in reasoning_content, content is null
REASONING_ONLY = [
    'data: {"choices":[{"delta":{"role":"assistant","content":null}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":"The"}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":" user"}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":" asks"}}]}',
    'data: {"choices":[],"usage":{"prompt_tokens":22,"completion_tokens":3}}',
    "data: [DONE]",
]

VLLM_REASONING_ONLY = [
    'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}',
    'data: {"choices":[{"delta":{"reasoning":"The"}}]}',
    'data: {"choices":[{"delta":{"reasoning":" answer"}}]}',
    'data: {"choices":[],"usage":{"prompt_tokens":15,"completion_tokens":2,'
    '"completion_tokens_details":{"reasoning_tokens":2}}}',
    "data: [DONE]",
]

MIXED = [
    'data: {"choices":[{"delta":{"reasoning_content":"Think"}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":" more"}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":" still"}}]}',
    'data: {"choices":[{"delta":{"content":"42"}}]}',
    'data: {"choices":[{"delta":{"content":"."}}]}',
    "data: [DONE]",
]


def test_reasoning_only_stream_reports_a_real_rate(monkeypatch):
    _stream(monkeypatch, REASONING_ONLY)

    result = OpenAICompatibleProvider().generate("m", "hi")

    assert result.speed.tokens_per_sec > 0     # was 0.00 before this feature
    assert result.speed.ttft_s > 0
    assert result.speed.output_tokens == 3
    assert result.text == ""                   # reasoning is not the answer


def test_vllm_reasoning_stream_reports_ttft_and_decode(monkeypatch):
    # vLLM 0.28 streams reasoning in delta.reasoning rather than the older
    # delta.reasoning_content extension. Both represent generated tokens.
    _stream(monkeypatch, VLLM_REASONING_ONLY, clock=[10.0, 10.5, 12.5])

    speed = VLLMProvider().generate("m", "hi").speed

    assert speed.reasoning_tokens == 2
    assert speed.output_tokens == 2
    assert speed.ttft_s == 0.5
    assert speed.eval_s == 2.0
    assert speed.tokens_per_sec == 1.0
    assert speed.prefill_tps is None


def test_ttft_is_taken_at_the_first_reasoning_token(monkeypatch):
    # clock: start=10.0, first token=10.5, end=12.5
    _stream(monkeypatch, REASONING_ONLY, clock=[10.0, 10.5, 12.5])

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.ttft_s == 0.5                 # the reasoning token set it
    assert speed.eval_s == 2.0
    assert speed.tokens_per_sec == 1.5         # 3 tokens / 2.0 s


def test_generation_text_carries_content_only(monkeypatch):
    _stream(monkeypatch, MIXED)

    result = OpenAICompatibleProvider().generate("m", "hi")

    assert result.text == "42."                # what the grader receives


def test_content_and_reasoning_token_counts_are_separate(monkeypatch):
    _stream(monkeypatch, MIXED)

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.content_tokens == 2
    assert speed.reasoning_tokens == 3

    _stream(monkeypatch, REASONING_ONLY)
    speed = OpenAICompatibleProvider().generate("m", "hi").speed
    assert speed.content_tokens == 0
    assert speed.reasoning_tokens == 3


def test_mixed_stream_counts_both_kinds_in_the_decode_window(monkeypatch):
    # clock: start=0.0, first token (reasoning)=1.0, end=6.0
    _stream(monkeypatch, MIXED, clock=[0.0, 1.0, 6.0])

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.output_tokens == 5            # 3 reasoning + 2 content
    assert speed.eval_s == 5.0                 # window opens at the reasoning
    assert speed.tokens_per_sec == 1.0         # 5 tokens / 5.0 s


# =====================================================================
# server-side timings drive prefill and decode (PERF-06..PERF-08)
# =====================================================================
# the wire shape llama.cpp b10664 sends in its final chunk
TIMINGS = {
    "cache_n": 0, "prompt_n": 22, "prompt_ms": 313.593,
    "prompt_per_token_ms": 14.25, "prompt_per_second": 70.15,
    "predicted_n": 12, "predicted_ms": 141.713,
    "predicted_per_token_ms": 12.88, "predicted_per_second": 77.62,
}


def _timed_stream(timings=TIMINGS, completion_tokens=2):
    final = {"choices": [],
             "usage": {"prompt_tokens": 22, "completion_tokens": completion_tokens}}
    if timings is not None:
        final["timings"] = timings
    return [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: " + json.dumps(final),
        "data: [DONE]",
    ]


def test_server_timings_supply_the_prefill_and_decode_rates(monkeypatch):
    _stream(monkeypatch, _timed_stream())

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.prefill_tps == 70.15          # timings.prompt_per_second
    assert speed.tokens_per_sec == 77.62       # timings.predicted_per_second
    assert speed.timings_source == "server"


def test_without_timings_the_rates_come_from_the_client(monkeypatch):
    # clock: start=0.0, first token=1.0, end=3.0 -> 2 tokens / 2.0 s
    _stream(monkeypatch, _timed_stream(timings=None), clock=[0.0, 1.0, 3.0])

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.tokens_per_sec == 1.0         # client stopwatch, not a server rate
    assert speed.prefill_tps is None           # never estimated
    assert speed.timings_source == "client"


def test_prompt_eval_s_comes_from_prompt_ms(monkeypatch):
    _stream(monkeypatch, _timed_stream())

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.prompt_eval_s == pytest.approx(0.313593)


def test_prompt_tokens_come_from_the_servers_prompt_n(monkeypatch):
    # the server processed 40 prompt tokens even though usage says 22
    timings = dict(TIMINGS, prompt_n=40)
    _stream(monkeypatch, _timed_stream(timings=timings))

    speed = OpenAICompatibleProvider().generate("m", "hi").speed

    assert speed.prompt_tokens == 40


def test_cache_n_is_preserved_for_the_caller(monkeypatch):
    _stream(monkeypatch, _timed_stream())
    assert OpenAICompatibleProvider().generate("m", "hi").cache_hit_tokens == 0

    _stream(monkeypatch, _timed_stream(timings=dict(TIMINGS, cache_n=1478)))
    result = OpenAICompatibleProvider().generate("m", "hi")
    assert result.cache_hit_tokens == 1478     # this prefill reused KV


# =====================================================================
# cache_prompt control on generate() (PERF-13)
# =====================================================================
def _capture_body(monkeypatch, lines):
    """Run generate() against a canned stream and return the JSON body sent."""
    import homebench.providers.openai_compat as mod
    sent = {}

    def fake_stream(*a, **k):
        sent.update(k.get("json") or {})
        return _FakeStream(lines)

    monkeypatch.setattr(mod.httpx, "stream", fake_stream)
    return sent


def test_cache_prompt_false_is_sent_in_the_request_body(monkeypatch):
    sent = _capture_body(monkeypatch, _timed_stream())

    OpenAICompatibleProvider().generate("m", "hi", cache_prompt=False)

    assert sent["cache_prompt"] is False


def test_cache_prompt_defaults_to_true_and_leaves_the_body_unchanged(monkeypatch):
    sent = _capture_body(monkeypatch, _timed_stream())

    OpenAICompatibleProvider().generate("m", "hi")

    assert "cache_prompt" not in sent           # byte-identical to before
    assert sent["model"] == "m"
    assert sent["stream"] is True


def test_every_provider_accepts_cache_prompt(monkeypatch):
    from homebench.providers.ollama import OllamaProvider
    from tests.fakes import FakeProvider

    # the in-memory provider the runner tests use
    assert FakeProvider().generate("fast:1b", "hi", cache_prompt=False).text

    # a provider with no such server-side knob still takes the argument
    ollama_lines = ['{"response":"hi","done":false}', '{"response":"","done":true}']
    import homebench.providers.ollama as omod
    monkeypatch.setattr(omod.httpx, "stream",
                        lambda *a, **k: _FakeStream(ollama_lines))
    assert OllamaProvider().generate("m", "hi", cache_prompt=False).text == "hi"


def test_base_provider_tokenize_returns_none(httpx_mock):
    # the default capability answers "I can't say" without asking anyone
    assert VLLMProvider().tokenize("m", "hello there") is None
    assert httpx_mock.get_requests() == []


# =====================================================================
# an error object streamed inside a 200 response is a failure, not silence
# =====================================================================
def test_in_stream_error_raises_instead_of_reporting_zero(monkeypatch):
    lines = [
        'data: {"error":{"code":500,"message":'
        '"the request exceeds the available context size"}}',
        "data: [DONE]",
    ]
    _stream(monkeypatch, lines)

    with pytest.raises(ProviderError) as excinfo:
        OpenAICompatibleProvider().generate("m", "hi")

    assert "context size" in str(excinfo.value)


def test_in_stream_error_after_partial_output_still_raises(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"par"}}]}',
        'data: {"error":"instance died"}',
        "data: [DONE]",
    ]
    _stream(monkeypatch, lines)

    with pytest.raises(ProviderError) as excinfo:
        OpenAICompatibleProvider().generate("m", "hi")

    assert "instance died" in str(excinfo.value)


def test_http_error_preserves_server_message(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/chat/completions",
        status_code=400,
        json={"error": {"message": "request exceeds the available context size"}},
    )

    with pytest.raises(ProviderError) as excinfo:
        OpenAICompatibleProvider().generate("m", "hi")

    message = str(excinfo.value)
    assert "400 Bad Request" in message
    assert "exceeds the available context size" in message
