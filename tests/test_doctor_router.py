"""`homebench doctor` diagnoses a llama.cpp router host (MLC-12)."""

import httpx

from homebench import doctor
from homebench.doctor import ROUTER_CHECK, Check, router_checks, run_checks

HOST = "http://router.test"
SECRET = "sk-super-secret-value"

PROPS = {"role": "router", "max_instances": 2, "models_autoload": False,
         "build_info": "b10615-f280b2698"}

MODELS = {"data": [
    {"id": "qwen35-4b", "status": {"value": "loaded", "args": ["-ngl", "99"]}},
    {"id": "llama32-3b", "status": {"value": "loaded", "args": []}},
    {"id": "gpt-oss-120b", "status": {"value": "unloaded", "args": []}},
]}


def _one(checks):
    assert len(checks) == 1
    return checks[0]


# =====================================================================
# reachable and authenticated
# =====================================================================
def test_reachable_router_is_ok_and_cites_build_and_resident_count(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=MODELS)

    check = _one(router_checks(host=HOST))

    assert check.name == ROUTER_CHECK
    assert check.status == "ok"
    assert "b10615-f280b2698" in check.detail
    assert "2 resident" in check.detail
    assert "qwen35-4b" in check.detail and "llama32-3b" in check.detail
    assert HOST in check.detail


def test_router_with_nothing_loaded_is_still_ok(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json={"data": []})

    check = _one(router_checks(host=HOST))

    assert check.status == "ok"
    assert "0 resident" in check.detail


# =====================================================================
# failure paths
# =====================================================================
def test_rejected_key_fails_without_showing_the_key(httpx_mock, monkeypatch):
    monkeypatch.setenv("LLAMACPP_API_KEY", SECRET)
    httpx_mock.add_response(
        url=f"{HOST}/props", status_code=401,
        json={"error": {"type": "authentication_error", "message": "Invalid API Key"}})

    check = _one(router_checks(host=HOST))

    assert check.status == "fail"
    assert SECRET not in check.detail
    assert "LLAMACPP_API_KEY" in check.detail        # says which key to check
    assert "authentication" in check.detail.lower()


def test_unreachable_router_fails_citing_the_host(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    check = _one(router_checks(host=HOST))

    assert check.status == "fail"
    assert HOST in check.detail
    assert "Traceback" not in check.detail


def test_listing_failure_after_a_good_props_fails(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", status_code=500,
                            json={"error": {"message": "boom"}})

    check = _one(router_checks(host=HOST))

    assert check.status == "fail"
    assert HOST in check.detail


def test_plain_llama_server_is_info_not_a_failure(httpx_mock):
    # a non-router llama.cpp host is a perfectly healthy setup
    httpx_mock.add_response(url=f"{HOST}/props", json={"model_path": "/m.gguf"})

    check = _one(router_checks(host=HOST))

    assert check.status == "info"
    assert "not a router" in check.detail


# =====================================================================
# doctor keeps working when no router is in play
# =====================================================================
def test_router_check_is_skipped_without_a_llamacpp_host(monkeypatch):
    monkeypatch.delenv("LLAMACPP_HOST", raising=False)
    assert doctor._router_expected([]) is False
    assert doctor._router_expected(["ollama", "lmstudio"]) is False


def test_router_check_runs_when_llamacpp_is_reachable(monkeypatch):
    monkeypatch.delenv("LLAMACPP_HOST", raising=False)
    assert doctor._router_expected(["ollama", "llamacpp"]) is True


def test_router_check_runs_when_the_host_is_configured(monkeypatch):
    monkeypatch.setenv("LLAMACPP_HOST", HOST)
    assert doctor._router_expected([]) is True


def test_doctor_omits_router_checks_when_none_is_expected(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "_router_expected", lambda names: False)
    checks = run_checks(home=str(tmp_path), check_pypi=False)
    assert ROUTER_CHECK not in {c.name for c in checks}
    assert next(c for c in checks if c.name == "Python").status == "ok"


def test_doctor_includes_router_checks_when_one_is_expected(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "_router_expected", lambda names: True)
    monkeypatch.setattr(doctor, "router_checks",
                        lambda host=None: [Check(ROUTER_CHECK, "ok", "probed")])
    checks = run_checks(home=str(tmp_path), check_pypi=False)
    router = next(c for c in checks if c.name == ROUTER_CHECK)
    assert router.detail == "probed"
