import httpx
import pytest

from homebench.lifecycle.router import LlamaRouterClient
from homebench.ops import RouterStatus, router_status

HOST = "http://router.test"
SECRET = "sk-secret"
PROPS = {"role": "router", "max_instances": 2, "build_info": "b10615-test"}
TWO_RESIDENTS = {
    "data": [
        {"id": "alpha", "status": {"value": "loaded", "args": []}},
        {"id": "beta", "status": {"value": "loaded", "args": []}},
        {"id": "gamma", "status": {"value": "unloaded", "args": []}},
    ]
}


def test_router_status_up_reports_host_build_and_two_residents(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=TWO_RESIDENTS)

    status = router_status(LlamaRouterClient(host=HOST))

    assert isinstance(status, RouterStatus)
    assert status.host == HOST
    assert status.reachable is True
    assert status.build_info == "b10615-test"
    assert status.resident_ids == ["alpha", "beta"]
    assert status.error is None


def test_router_status_down_is_not_reachable(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    status = router_status(LlamaRouterClient(host=HOST, api_key=SECRET))

    assert status.reachable is False
    assert status.host == HOST
    assert status.error
    assert SECRET not in status.error


def test_router_status_401_hides_api_key(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", status_code=401)

    status = router_status(LlamaRouterClient(host=HOST, api_key=SECRET))

    assert status.reachable is False
    assert status.error
    assert SECRET not in status.error
