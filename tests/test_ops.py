import httpx
import pytest

from homebench.doctor import Check
from homebench.history import save_run
from homebench.lifecycle.router import LlamaRouterClient
from homebench.models import BenchmarkResult, ModelInfo, ModelReport, SpeedMetrics
from homebench.ops import RouterStatus, doctor_snapshot, history_snapshot, router_status

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


def test_doctor_snapshot_preserves_ok_and_fail_checks(monkeypatch):
    checks = [
        Check("router", "ok", "reachable"),
        Check("models", "fail", "none found"),
    ]
    monkeypatch.setattr("homebench.ops.doctor.run_checks", lambda **kwargs: checks)

    snapshot = doctor_snapshot()

    assert snapshot == checks
    assert snapshot[0].status == "ok"
    assert snapshot[1].status == "fail"


def test_history_snapshot_empty_home_returns_empty_list(tmp_path):
    home = str(tmp_path / "home")
    assert history_snapshot(home=home) == []


def _make_result(started_at, name):
    report = ModelReport(model=ModelInfo(name, "llamacpp", size_bytes=1))
    report.speed = SpeedMetrics(tokens_per_sec=10.0, ttft_s=0.1)
    return BenchmarkResult(reports=[report], provider="llamacpp", started_at=started_at)


def test_history_snapshot_returns_two_runs_newest_first(tmp_path):
    home = str(tmp_path / "home")
    save_run(_make_result(1000.0, "alpha"), home=home)
    save_run(_make_result(2000.0, "beta"), home=home)

    runs = history_snapshot(home=home)

    assert len(runs) == 2
    assert runs[0].started_at == 2000.0
    assert runs[1].started_at == 1000.0
    assert runs[0].model_names == ["beta"]
    assert runs[1].model_names == ["alpha"]
