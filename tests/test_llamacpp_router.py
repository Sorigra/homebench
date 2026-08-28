"""The llamacpp provider gets a real unload() when its host is a router.

Offline via pytest-httpx. Requirement: MLC-14 (real unload, best-effort,
no-op off-router), AD-004 (capability probed per host, never cached globally).
"""

import json

import httpx
import pytest

from homebench.providers import (
    LlamaCppProvider,
    LMStudioProvider,
    OpenAICompatibleProvider,
    VLLMProvider,
)

ROUTER = "http://router.test"
PLAIN = "http://plain.test"

PROPS_ROUTER = {"role": "router", "max_instances": 2, "build_info": "b10615"}


def _router_provider(httpx_mock, host=ROUTER):
    httpx_mock.add_response(url=f"{host}/props", json=PROPS_ROUTER)
    return LlamaCppProvider(host=host)


def _unload_requests(httpx_mock):
    return [r for r in httpx_mock.get_requests()
            if r.url.path == "/models/unload"]


# =====================================================================
# unload() on a router host
# =====================================================================
def test_unload_posts_models_unload_on_a_router_host(httpx_mock):
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(url=f"{ROUTER}/models/unload", json={"success": True})

    provider.unload("qwen35-4b")

    posts = _unload_requests(httpx_mock)
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {"model": "qwen35-4b"}
    assert provider.last_unload_error is None


def test_unload_failure_is_recorded_and_does_not_raise(httpx_mock):
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(
        url=f"{ROUTER}/models/unload", status_code=500,
        json={"error": {"message": "instance busy"}},
    )

    provider.unload("qwen35-4b")  # best-effort: the run must continue

    assert provider.last_unload_error
    assert "instance busy" in provider.last_unload_error


def test_unload_network_failure_does_not_raise(httpx_mock):
    httpx_mock.add_response(url=f"{ROUTER}/props", json=PROPS_ROUTER)
    provider = LlamaCppProvider(host=ROUTER)
    httpx_mock.add_exception(httpx.ConnectError("router went away"))

    provider.unload("qwen35-4b")

    assert provider.last_unload_error and ROUTER in provider.last_unload_error


def test_unload_sends_the_api_key_when_configured(httpx_mock, monkeypatch):
    monkeypatch.setenv("LLAMACPP_API_KEY", "sk-secret")
    httpx_mock.add_response(url=f"{ROUTER}/props", json=PROPS_ROUTER)
    httpx_mock.add_response(url=f"{ROUTER}/models/unload", json={"success": True})

    LlamaCppProvider(host=ROUTER).unload("qwen35-4b")

    assert _unload_requests(httpx_mock)[0].headers["Authorization"] == "Bearer sk-secret"


# =====================================================================
# non-router hosts keep the inherited no-op
# =====================================================================
def test_unload_is_a_silent_noop_when_the_host_is_not_a_router(httpx_mock):
    httpx_mock.add_response(url=f"{PLAIN}/props", json={"model_path": "/m.gguf"})
    provider = LlamaCppProvider(host=PLAIN)

    provider.unload("qwen35-4b")  # must not raise

    assert _unload_requests(httpx_mock) == []
    assert provider.last_unload_error is None


def test_unload_is_a_noop_when_props_is_unreachable(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("nothing listening"))
    provider = LlamaCppProvider(host=PLAIN)

    provider.unload("qwen35-4b")

    assert _unload_requests(httpx_mock) == []


# =====================================================================
# AD-004: the probe is per host/instance, never a global cache
# =====================================================================
def test_router_capability_is_probed_per_instance(httpx_mock):
    httpx_mock.add_response(url=f"{ROUTER}/props", json=PROPS_ROUTER)
    httpx_mock.add_response(url=f"{PLAIN}/props", json={"role": "server"})
    httpx_mock.add_response(url=f"{ROUTER}/models/unload", json={"success": True})

    router_host = LlamaCppProvider(host=ROUTER)
    plain_host = LlamaCppProvider(host=PLAIN)

    assert router_host.router() is not None
    assert plain_host.router() is None      # the first host's answer must not leak
    router_host.unload("m")
    plain_host.unload("m")
    assert len(_unload_requests(httpx_mock)) == 1


def test_a_second_instance_reprobes_the_same_host(httpx_mock):
    httpx_mock.add_response(url=f"{ROUTER}/props", json={"role": "server"})
    assert LlamaCppProvider(host=ROUTER).router() is None
    httpx_mock.add_response(url=f"{ROUTER}/props", json=PROPS_ROUTER)
    assert LlamaCppProvider(host=ROUTER).router() is not None


def test_router_is_probed_only_once_per_instance(httpx_mock):
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(url=f"{ROUTER}/models/unload", json={"success": True})
    httpx_mock.add_response(url=f"{ROUTER}/models/unload", json={"success": True})

    provider.unload("a")
    provider.unload("b")

    props = [r for r in httpx_mock.get_requests() if r.url.path == "/props"]
    assert len(props) == 1


# =====================================================================
# regression: the other providers are untouched
# =====================================================================
@pytest.mark.parametrize("cls", [OpenAICompatibleProvider, VLLMProvider,
                                 LMStudioProvider])
def test_other_openai_compatible_providers_still_noop_unload(cls, httpx_mock):
    provider = cls(host=ROUTER)

    assert provider.unload("qwen35-4b") is None

    assert httpx_mock.get_requests() == []   # no /props probe, no /models/unload


def test_ollama_unload_is_unchanged(httpx_mock):
    from homebench.providers import OllamaProvider

    httpx_mock.add_response(url="http://ollama.test/api/generate", json={})
    OllamaProvider(host="http://ollama.test").unload("llama3.2")

    paths = [r.url.path for r in httpx_mock.get_requests()]
    assert paths == ["/api/generate"]        # still its own keep_alive=0 call


# =====================================================================
# tokenize(): exact prompt-token counts, None when the host can't say
# Requirement: PERF-12 (support)
# =====================================================================
def test_tokenize_counts_the_tokens_the_server_returns(httpx_mock):
    httpx_mock.add_response(url=f"{PLAIN}/tokenize",
                            json={"tokens": [818, 3823, 17354, 39935, 35308]})

    provider = LlamaCppProvider(host=PLAIN)
    assert provider.tokenize("gemma4-e2b", "The quick brown fox jumps") == 5

    posts = [r for r in httpx_mock.get_requests() if r.url.path == "/tokenize"]
    assert json.loads(posts[0].content) == {
        "model": "gemma4-e2b", "content": "The quick brown fox jumps",
    }


def test_tokenize_is_none_when_the_model_is_not_loaded(httpx_mock):
    httpx_mock.add_response(
        url=f"{PLAIN}/tokenize", status_code=400,
        json={"error": {"code": 400, "message": "model is not loaded"}},
    )

    # a measurement must not die because a model is not resident yet
    assert LlamaCppProvider(host=PLAIN).tokenize("gemma4-e2b", "hi") is None


def test_tokenize_is_none_when_the_route_or_the_host_is_missing(httpx_mock):
    # some builds don't serve /tokenize at all
    httpx_mock.add_response(url=f"{PLAIN}/tokenize", status_code=404)
    assert LlamaCppProvider(host=PLAIN).tokenize("m", "hi") is None

    httpx_mock.add_exception(httpx.ConnectError("no route"), url=f"{PLAIN}/tokenize")
    assert LlamaCppProvider(host=PLAIN).tokenize("m", "hi") is None
