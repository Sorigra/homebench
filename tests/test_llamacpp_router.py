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


# =====================================================================
# memory(): the footprint comes from the GGUF the router resolved
# =====================================================================
def _models_response(model_path, model="qwen35-4b"):
    return {"data": [{
        "id": model,
        "status": {
            "value": "unloaded",
            "args": ["/usr/bin/llama-server", "--model", model_path,
                     "--n-gpu-layers", "999"],
        },
    }]}


def _gguf(directory, name, size):
    path = directory / name
    path.write_bytes(b"\0" * size)
    return path


def test_memory_reports_the_size_of_the_model_file(httpx_mock, tmp_path):
    gguf = _gguf(tmp_path, "qwen35-4b.gguf", 4096)
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(url=f"{ROUTER}/v1/models",
                            json=_models_response(str(gguf)))

    assert provider.memory("qwen35-4b").size_bytes == 4096


def test_memory_maps_a_container_path_through_homebench_model_dir(
        httpx_mock, tmp_path, monkeypatch):
    # the server reports /models/qwen35-4b/w.gguf; the host mounts it from
    # tmp_path, and the mount point itself is not discoverable over HTTP
    host_dir = tmp_path / "ai-models" / "qwen35-4b"
    host_dir.mkdir(parents=True)
    _gguf(host_dir, "w.gguf", 2048)
    monkeypatch.setenv("HOMEBENCH_MODEL_DIR", str(tmp_path / "ai-models"))

    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(
        url=f"{ROUTER}/v1/models",
        json=_models_response("/models/qwen35-4b/w.gguf"))

    assert provider.memory("qwen35-4b").size_bytes == 2048


def test_memory_sums_every_shard_of_a_split_gguf(httpx_mock, tmp_path):
    for n in (1, 2, 3):
        _gguf(tmp_path, "big-%05d-of-00003.gguf" % n, 1000)
    first = tmp_path / "big-00001-of-00003.gguf"
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(url=f"{ROUTER}/v1/models",
                            json=_models_response(str(first)))

    assert provider.memory("qwen35-4b").size_bytes == 3000


def test_memory_is_empty_when_the_file_cannot_be_reached(
        httpx_mock, tmp_path, monkeypatch):
    monkeypatch.delenv("HOMEBENCH_MODEL_DIR", raising=False)
    provider = _router_provider(httpx_mock)
    httpx_mock.add_response(
        url=f"{ROUTER}/v1/models",
        json=_models_response("/models/qwen35-4b/w.gguf"))

    # blank beats a guess: an unreachable path is not a footprint of zero
    assert provider.memory("qwen35-4b").size_bytes == 0


def test_memory_is_empty_off_router(httpx_mock):
    httpx_mock.add_response(url=f"{PLAIN}/props", json={"role": "server"})

    assert LlamaCppProvider(host=PLAIN).memory("qwen35-4b").size_bytes == 0


# =====================================================================
# The served context window, not the one the argv asked for (PERF-14)
# =====================================================================
def test_context_window_reads_the_served_n_ctx(httpx_mock):
    """/props answers with the loaded instance's own n_ctx.

    That number is already divided by --parallel and already capped at the
    model's trained context, which is exactly what the argv cannot say.
    """
    httpx_mock.add_response(
        url="http://x:8080/props?model=gemma4-e2b",
        json={"default_generation_settings": {"n_ctx": 4096}},
    )
    assert LlamaCppProvider(host="http://x:8080").context_window("gemma4-e2b") == 4096


def test_context_window_is_none_when_the_route_is_missing(httpx_mock):
    httpx_mock.add_response(url="http://x:8080/props?model=m", status_code=404)
    assert LlamaCppProvider(host="http://x:8080").context_window("m") is None


def test_context_window_is_none_on_a_malformed_answer(httpx_mock):
    httpx_mock.add_response(url="http://x:8080/props?model=m",
                            json={"default_generation_settings": {"n_ctx": 0}})
    assert LlamaCppProvider(host="http://x:8080").context_window("m") is None


def test_context_window_is_none_when_props_says_nothing_about_ctx(httpx_mock):
    httpx_mock.add_response(url="http://x:8080/props?model=m",
                            json={"role": "router", "max_instances": 3})
    assert LlamaCppProvider(host="http://x:8080").context_window("m") is None
