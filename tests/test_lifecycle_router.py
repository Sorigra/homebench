"""LlamaRouterClient - HTTP client for the llama.cpp router.

All tests run offline via pytest-httpx. Requirements exercised so far:
MLC-02 (missing model cited), MLC-06/MLC-13 (load/unload, 404 = missing file,
router message propagated), MLC-07 (auth rejected, key never echoed),
MLC-10/MLC-11 (unreachable), AD-004 (positive router detection).
"""

import json

import httpx
import pytest

from homebench.lifecycle.router import LlamaRouterClient
from homebench.providers.base import ProviderError

HOST = "http://router.test"

SECRET_KEY = "sk-super-secret-value-1234"


def _client(**kw):
    kw.setdefault("host", HOST)
    return LlamaRouterClient(**kw)


# =====================================================================
# T2: props() and is_router()
# =====================================================================
PROPS_OK = {
    "role": "router",
    "max_instances": 2,
    "models_autoload": False,
    "build_info": "b10615-f280b2698",
}


def test_props_returns_routerinfo(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS_OK)
    info = _client().props()
    assert info.role == "router"
    assert info.max_instances == 2
    assert info.build_info == "b10615-f280b2698"


def test_props_401_raises_auth_error_without_echoing_key(httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/props",
        status_code=401,
        json={"error": {"type": "authentication_error", "message": "Invalid API Key"}},
    )
    with pytest.raises(ProviderError) as exc:
        _client(api_key=SECRET_KEY).props()
    msg = str(exc.value)
    assert "authentication" in msg.lower() or "auth" in msg.lower()
    assert SECRET_KEY not in msg


def test_props_404_raises_providererror(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", status_code=404, text="Not Found")
    with pytest.raises(ProviderError):
        _client().props()


def test_props_invalid_json_raises_providererror(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", text="<html>not json</html>")
    with pytest.raises(ProviderError):
        _client().props()


def test_props_network_error_raises_providererror_citing_host(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    with pytest.raises(ProviderError) as exc:
        _client().props()
    assert HOST in str(exc.value)


def test_is_router_true_when_role_is_router(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS_OK)
    assert _client().is_router() is True


def test_is_router_false_when_role_missing(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json={"max_instances": 1})
    assert _client().is_router() is False


def test_is_router_false_when_role_is_not_router(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json={"role": "server"})
    assert _client().is_router() is False


def test_is_router_false_on_404(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", status_code=404)
    assert _client().is_router() is False


def test_is_router_false_on_invalid_json(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", text="nonsense")
    assert _client().is_router() is False


def test_is_router_false_on_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("no route to host"))
    assert _client().is_router() is False


def test_is_router_false_on_401(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", status_code=401)
    assert _client().is_router() is False


# ---- constructor / host + key resolution -----------------------------
def test_host_is_normalised():
    assert LlamaRouterClient(host="router.test:8080").host == "http://router.test:8080"
    assert LlamaRouterClient(host="https://x:1/").host == "https://x:1"


def test_host_and_key_come_from_env(monkeypatch):
    monkeypatch.setenv("LLAMACPP_HOST", "http://box:9999")
    monkeypatch.setenv("LLAMACPP_API_KEY", "env-key")
    c = LlamaRouterClient()
    assert c.host == "http://box:9999"
    assert c.api_key == "env-key"


def test_explicit_key_beats_env(monkeypatch):
    monkeypatch.setenv("LLAMACPP_API_KEY", "env-key")
    assert LlamaRouterClient(host=HOST, api_key="explicit").api_key == "explicit"


def test_auth_header_present_only_with_key():
    assert _client(api_key="k")._headers() == {"Authorization": "Bearer k"}
    assert _client()._headers() == {}


# =====================================================================
# T3: list_models() and loaded_models()
# =====================================================================
def _entry(model_id, value, ngl, source="models_dir", preset=None):
    return {
        "id": model_id,
        "object": "model",
        "created": 1730000000,
        "owned_by": "llamacpp",
        "source": source,
        "status": {
            "value": value,
            "args": ["/app/llama-server", "-m", f"/models/{model_id}.gguf", "-ngl", str(ngl)],
            "preset": preset if preset is not None else model_id,
        },
    }


# Faithful reconstruction of GET /v1/models for a --models-max 2 router with 17
# models (2 loaded, 1 loading, 14 unloaded). The design records the contract
# (data[].status.value, data[].status.args, data[].source) but not a captured
# body, so this fixture is built from that contract (AD-001).
V1_MODELS_17 = {
    "object": "list",
    "data": [
        _entry("qwen35-4b", "loaded", 99),
        _entry("llama32-3b", "loaded", 99),
        _entry("qwen35-14b", "loading", 99),
        _entry("gemma2-9b", "unloaded", 99),
        _entry("gemma2-27b", "unloaded", 46),
        _entry("mistral-7b", "unloaded", 99),
        _entry("mixtral-8x7b", "unloaded", 20),
        _entry("phi3-mini", "unloaded", 99),
        _entry("phi3-medium", "unloaded", 99),
        _entry("deepseek-r1-7b", "unloaded", 99),
        _entry("deepseek-r1-32b", "unloaded", 30),
        _entry("qwen35-coder-7b", "unloaded", 99),
        _entry("qwen35-coder-32b", "unloaded", 30),
        _entry("llama33-70b", "unloaded", 40),
        _entry("command-r-35b", "unloaded", 28),
        _entry("gpt-oss-120b", "unloaded", 12, source="preset", preset="gpt-oss"),
        _entry("yi-34b", "unloaded", 34),
    ],
}


def test_list_models_returns_state_args_preset_source(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=V1_MODELS_17)
    models = _client().list_models()
    assert len(models) == 17
    by_id = {m.id: m for m in models}
    assert by_id["qwen35-4b"].status == "loaded"
    assert by_id["qwen35-14b"].status == "loading"
    assert by_id["gpt-oss-120b"].preset == "gpt-oss"
    assert by_id["gpt-oss-120b"].source == "preset"
    assert by_id["qwen35-4b"].args == [
        "/app/llama-server", "-m", "/models/qwen35-4b.gguf", "-ngl", "99",
    ]


def test_list_models_populates_args_for_unloaded_models(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=V1_MODELS_17)
    models = _client().list_models()
    unloaded = [m for m in models if m.status == "unloaded"]
    assert len(unloaded) == 14
    assert all(m.args for m in unloaded)
    assert next(m for m in unloaded if m.id == "gemma2-27b").args[-2:] == ["-ngl", "46"]


def test_loaded_models_filters_to_loaded_only(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=V1_MODELS_17)
    loaded = _client().loaded_models()
    assert sorted(m.id for m in loaded) == ["llama32-3b", "qwen35-4b"]
    assert all(m.status == "loaded" for m in loaded)


def test_list_models_401_raises_providererror(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", status_code=401)
    with pytest.raises(ProviderError):
        _client(api_key=SECRET_KEY).list_models()


def test_list_models_network_failure_raises_providererror_citing_host(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("down"))
    with pytest.raises(ProviderError) as exc:
        _client().list_models()
    assert HOST in str(exc.value)


def test_list_models_skips_entries_without_id(httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/v1/models",
        json={"data": [{"status": {"value": "loaded"}}, _entry("real", "loaded", 99)]},
    )
    models = _client().list_models()
    assert [m.id for m in models] == ["real"]


# =====================================================================
# T4: load() and unload()
# =====================================================================
def _sent_body(httpx_mock):
    reqs = httpx_mock.get_requests()
    assert len(reqs) == 1
    return json.loads(reqs[0].content)


def test_load_sends_model_only_when_no_extra_args(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/load", json={"success": True})
    _client().load("qwen35-4b")
    assert _sent_body(httpx_mock) == {"model": "qwen35-4b"}


def test_load_includes_extra_args_when_given(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/load", json={"success": True})
    _client().load("qwen35-4b", extra_args=["-ngl", "20", "-fa"])
    assert _sent_body(httpx_mock) == {
        "model": "qwen35-4b",
        "extra_args": ["-ngl", "20", "-fa"],
    }


def test_load_omits_extra_args_when_empty_list(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/load", json={"success": True})
    _client().load("qwen35-4b", extra_args=[])
    assert _sent_body(httpx_mock) == {"model": "qwen35-4b"}


def test_unload_sends_model(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/unload", json={"success": True})
    _client().unload("qwen35-4b")
    assert _sent_body(httpx_mock) == {"model": "qwen35-4b"}


def test_load_404_is_missing_model_file_citing_id_not_route(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/load", status_code=404, text="File Not Found")
    with pytest.raises(ProviderError) as exc:
        _client().load("ghost-model")
    msg = str(exc.value).lower()
    assert "ghost-model" in str(exc.value)
    # interpreted as a missing model *file*, never as a missing route/endpoint
    assert "model file not found" in msg
    assert "route not found" not in msg and "no such endpoint" not in msg


def test_load_400_unknown_model_cites_id_and_propagates_router_message(httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/models/load",
        status_code=400,
        json={"error": {"message": "unknown model id: ghost-model", "type": "invalid_request_error"}},
    )
    with pytest.raises(ProviderError) as exc:
        _client().load("ghost-model")
    text = str(exc.value)
    assert "ghost-model" in text
    assert "unknown model id: ghost-model" in text  # router's own words, unmodified


def test_load_401_raises_auth_error_without_key(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/load", status_code=401)
    with pytest.raises(ProviderError) as exc:
        _client(api_key=SECRET_KEY).load("m")
    assert SECRET_KEY not in str(exc.value)


def test_unload_404_is_missing_model_file_citing_id(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/models/unload", status_code=404)
    with pytest.raises(ProviderError) as exc:
        _client().unload("ghost-model")
    assert "ghost-model" in str(exc.value)


def test_load_network_failure_cites_host(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(ProviderError) as exc:
        _client().load("m")
    assert HOST in str(exc.value)
