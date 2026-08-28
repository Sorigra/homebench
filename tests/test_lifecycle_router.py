"""LlamaRouterClient - HTTP client for the llama.cpp router.

All tests run offline via pytest-httpx. Requirements exercised so far:
MLC-07 (auth rejected, key never echoed), MLC-10/MLC-11 (unreachable),
AD-004 (positive router detection).
"""

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
