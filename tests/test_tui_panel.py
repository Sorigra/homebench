import asyncio
import json
import os
from pathlib import Path

from textual.widgets import Static

from homebench.config import HomebenchConfig, load, save
from homebench.doctor import Check
from homebench.history import RunRecord
from homebench.ops import RouterStatus
from homebench.tui.panel import (
    PanelApp,
    format_status_strip,
    model_checkbox_id,
    run_panel,
)

HOST = "http://router.test"
SECRET = "sk-secret"


def test_format_status_strip_down_shows_host():
    text = format_status_strip(
        RouterStatus(host=HOST, reachable=False, error="auth failed")
    )
    assert HOST in text
    assert "down" in text


def test_format_status_strip_up_shows_build_and_residents():
    text = format_status_strip(
        RouterStatus(
            host=HOST,
            reachable=True,
            build_info="b10615",
            resident_ids=["alpha", "beta"],
        )
    )
    assert "up" in text
    assert "b10615" in text
    assert "alpha" in text
    assert "beta" in text


def test_domain_modules_do_not_import_tui():
    root = Path(__file__).resolve().parents[1] / "src" / "homebench"
    for name in ("config.py", "plan.py", "ops.py"):
        source = (root / name).read_text()
        assert "tui" not in source


async def _strip_text(app: PanelApp) -> str:
    widget = app.query_one("#status-strip")
    return str(widget.render())


def test_panel_status_strip_shows_down_and_hides_secret():
    status = RouterStatus(
        host=HOST,
        reachable=False,
        error=f"401 unauthorized with {SECRET}",
    )

    async def scenario():
        app = PanelApp(status=status)
        async with app.run_test() as pilot:
            text = await _strip_text(app)
            assert HOST in text
            assert "down" in text
            assert SECRET not in text
            await pilot.press("q")

    asyncio.run(scenario())


def test_panel_quit_returns_none():
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status)
        async with app.run_test() as pilot:
            await pilot.press("q")
        assert app.result is None

    asyncio.run(scenario())


async def _open_plan(app: PanelApp, pilot):
    await pilot.press("p")
    await pilot.pause(0.05)


async def _click_model(pilot, app: PanelApp, model_id: str) -> None:
    index = list(app._model_ids or []).index(model_id)
    await pilot.click(f"#{model_checkbox_id(index)}")


def test_plan_screen_two_models_in_plan(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True, build_info="b1")
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await _click_model(pilot, app, "alpha")
            await _click_model(pilot, app, "beta")
            await pilot.click("#depth-0")
            plan = app._read_plan_from_ui()
            assert plan.model_ids == ["alpha", "beta"]
            assert plan.depths == [0]

    asyncio.run(scenario())


def test_plan_empty_catalog_shows_no_models_and_refuses_run(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True)

    async def scenario():
        app = PanelApp(status=status, model_ids=[], home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            assert len(list(app.query("#model-list Checkbox"))) == 0
            await pilot.click("#run-btn")
            await pilot.pause(0.05)
            msg = app.query_one("#plan-message", Static)
            assert "modelo" in str(msg.render()).lower()
            assert app.result is None

    asyncio.run(scenario())


def test_plan_run_with_zero_models_shows_message_and_stays(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True)
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await pilot.click("#run-btn")
            await pilot.pause(0.05)
            msg = app.query_one("#plan-message", Static)
            assert "modelo" in str(msg.render()).lower()
            assert app.result is None

    asyncio.run(scenario())


def test_plan_run_with_zero_depths_shows_message(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True)
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await _click_model(pilot, app, "alpha")
            await pilot.click("#run-btn")
            await pilot.pause(0.05)
            msg = app.query_one("#plan-message", Static)
            assert "profundidade" in str(msg.render()).lower()

    asyncio.run(scenario())


def test_last_plan_persists_and_restores_dropping_stale_ids(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    save(
        HomebenchConfig(
            host=HOST,
            last_plan={
                "model_ids": ["alpha", "gone"],
                "depths": [0, 8192],
                "run_speed": True,
                "run_quality": False,
            },
        ),
        home=home,
    )
    status = RouterStatus(host=HOST, reachable=True)
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            plan = app._read_plan_from_ui()
            assert plan.model_ids == ["alpha"]
            assert plan.depths == [0, 8192]

    asyncio.run(scenario())


def test_valid_plan_saved_on_run(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True)
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await _click_model(pilot, app, "alpha")
            await _click_model(pilot, app, "beta")
            await pilot.click("#depth-0")
            await pilot.click("#run-btn")
            await pilot.pause(0.05)

    asyncio.run(scenario())
    cfg = load(home=home)
    assert cfg.last_plan is not None
    assert cfg.last_plan["model_ids"] == ["alpha", "beta"]
    assert cfg.last_plan["depths"] == [0]


def test_plan_accepts_model_ids_with_dots(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True)
    dotted = "qwen3.8-27b-unsloth"
    underscore = "qwen3_8-27b-unsloth"
    model_ids = [dotted, underscore]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            labels = [str(cb.label) for cb in app.query("#model-list Checkbox")]
            assert labels == model_ids
            await _click_model(pilot, app, dotted)
            await _click_model(pilot, app, underscore)
            await pilot.click("#depth-0")
            plan = app._read_plan_from_ui()
            assert plan.model_ids == [dotted, underscore]
            await pilot.click("#run-btn")
            await pilot.pause(0.05)
            assert app.result is not None
            assert app.result.model_ids == [dotted, underscore]

    asyncio.run(scenario())
    cfg = load(home=home)
    assert cfg.last_plan is not None
    assert cfg.last_plan["model_ids"] == [dotted, underscore]


def test_last_plan_restores_model_ids_with_dots(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    dotted = "qwen3.8-27b-unsloth"
    save(
        HomebenchConfig(
            host=HOST,
            last_plan={
                "model_ids": [dotted],
                "depths": [0],
                "run_speed": True,
                "run_quality": False,
            },
        ),
        home=home,
    )
    status = RouterStatus(host=HOST, reachable=True)

    async def scenario():
        app = PanelApp(status=status, model_ids=[dotted, "alpha"], home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            plan = app._read_plan_from_ui()
            assert plan.model_ids == [dotted]
            assert plan.depths == [0]

    asyncio.run(scenario())


def test_doctor_screen_shows_ok_and_fail_checks(monkeypatch):
    checks = [
        Check("router", "ok", "reachable"),
        Check("models", "fail", "none found"),
    ]
    monkeypatch.setattr("homebench.tui.panel.doctor_snapshot", lambda: checks)
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("d")
            await pilot.pause(0.05)
            body = app.query_one("#doctor-body", Static)
            text = str(body.render())
            assert "ok: router" in text
            assert "fail: models" in text

    asyncio.run(scenario())


def test_history_empty_shows_message(monkeypatch):
    monkeypatch.setattr("homebench.tui.panel.history_snapshot", lambda home=None: [])
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("h")
            await pilot.pause(0.05)
            body = app.query_one("#history-body", Static)
            assert "não há runs" in str(body.render()).lower()

    asyncio.run(scenario())


def test_history_shows_two_runs_newest_first(monkeypatch):
    runs = [
        RunRecord("new.json", {"started_at": 2000.0, "provider": "llamacpp",
                               "reports": [{"model": {"name": "beta"}}]}),
        RunRecord("old.json", {"started_at": 1000.0, "provider": "llamacpp",
                               "reports": [{"model": {"name": "alpha"}}]}),
    ]
    monkeypatch.setattr("homebench.tui.panel.history_snapshot", lambda home=None: runs)
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("h")
            await pilot.pause(0.05)
            text = str(app.query_one("#history-body", Static).render())
            assert "beta" in text
            assert "alpha" in text
            assert text.index("beta") < text.index("alpha")

    asyncio.run(scenario())


def test_doctor_and_history_screens_do_not_call_router(monkeypatch):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("router HTTP not allowed on doctor/history screens")

    monkeypatch.setattr(
        "homebench.lifecycle.router.LlamaRouterClient.list_models",
        _forbidden,
    )
    monkeypatch.setattr(
        "homebench.lifecycle.router.LlamaRouterClient.props",
        _forbidden,
    )
    monkeypatch.setattr(
        "homebench.tui.panel.doctor_snapshot",
        lambda: [Check("router", "ok", "fine"), Check("disk", "ok", "fine")],
    )
    monkeypatch.setattr("homebench.tui.panel.history_snapshot", lambda home=None: [])
    status = RouterStatus(host=HOST, reachable=True, build_info="b1")

    async def scenario():
        app = PanelApp(status=status, model_ids=["alpha", "beta"])
        async with app.run_test() as pilot:
            await pilot.press("d")
            await pilot.pause(0.05)
            await pilot.press("m")
            await pilot.press("h")
            await pilot.pause(0.05)

    asyncio.run(scenario())


async def _run_valid_plan(app, pilot, model_ids=("alpha",)):
    await _open_plan(app, pilot)
    for mid in model_ids:
        await _click_model(pilot, app, mid)
    await pilot.click("#depth-0")
    await pilot.click("#run-btn")
    await pilot.pause(0.2)


def test_run_refused_when_foreign_residents_and_confirmer_false(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(
        host=HOST, reachable=True, resident_ids=["foreign", "alpha"]
    )
    unload_calls = []
    monkeypatch.setattr(
        "homebench.lifecycle.router.LlamaRouterClient.unload",
        lambda self, model: unload_calls.append(model),
    )

    async def scenario():
        app = PanelApp(
            status=status,
            model_ids=["alpha", "beta"],
            home=home,
            confirmer=lambda _foreign: False,
        )
        async with app.run_test() as pilot:
            await _run_valid_plan(app, pilot)
            assert app.result is None

    asyncio.run(scenario())
    assert unload_calls == []


def test_run_returns_plan_when_confirmer_accepts_foreign(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True, resident_ids=["foreign"])

    async def scenario():
        app = PanelApp(
            status=status,
            model_ids=["alpha", "beta"],
            home=home,
            confirmer=lambda foreign: foreign == ["foreign"],
        )
        async with app.run_test() as pilot:
            await _run_valid_plan(app, pilot)
            assert app.result is not None
            assert app.result.model_ids == ["alpha"]
            assert app.result.depths == [0]

    asyncio.run(scenario())


def test_run_returns_plan_without_confirm_when_no_foreigners(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True, resident_ids=["alpha"])

    async def scenario():
        app = PanelApp(status=status, model_ids=["alpha", "beta"], home=home)
        async with app.run_test() as pilot:
            await _run_valid_plan(app, pilot)
            assert app.result is not None
            assert app.result.model_ids == ["alpha"]

    asyncio.run(scenario())


def test_panel_does_not_invoke_runner(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("Runner must not be called from the panel")

    monkeypatch.setattr("homebench.runner.Runner.run", _forbidden)
    monkeypatch.setattr("homebench.tui.app.run_tui", _forbidden)
    status = RouterStatus(host=HOST, reachable=True, resident_ids=[])

    async def scenario():
        app = PanelApp(status=status, model_ids=["alpha", "beta"], home=home)
        async with app.run_test() as pilot:
            await _run_valid_plan(app, pilot)

    asyncio.run(scenario())


def test_run_panel_returns_none_on_quit():
    status = RouterStatus(host=HOST, reachable=True, build_info="b1")

    async def scenario():
        app = PanelApp(status=status)
        async with app.run_test() as pilot:
            await pilot.press("q")

    asyncio.run(scenario())
    # run_panel blocks; verify via PanelApp directly above and function wrapper:
    status2 = RouterStatus(host=HOST, reachable=False)

    def fake_run(self):
        self.exit(None)

    import homebench.tui.panel as panel_mod

    original = PanelApp.run
    PanelApp.run = fake_run  # type: ignore[method-assign]
    try:
        assert run_panel(status=status2) is None
    finally:
        PanelApp.run = original


def _view_hidden(app: PanelApp, name: str) -> bool:
    return app.query_one(f"#{name}-view").has_class("hidden")


def test_menu_enter_opens_plan():
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=["alpha"])
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert _view_hidden(app, "menu")
            assert not _view_hidden(app, "plan")

    asyncio.run(scenario())


def test_menu_down_enter_opens_doctor(monkeypatch):
    monkeypatch.setattr(
        "homebench.tui.panel.doctor_snapshot",
        lambda: [Check("router", "ok", "fine")],
    )
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert _view_hidden(app, "menu")
            assert not _view_hidden(app, "doctor")
            text = str(app.query_one("#doctor-body", Static).render())
            assert "ok: router" in text

    asyncio.run(scenario())


def test_escape_from_plan_returns_to_menu():
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=["alpha"])
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await pilot.press("escape")
            await pilot.pause(0.05)
            assert not _view_hidden(app, "menu")
            assert _view_hidden(app, "plan")
            assert app.result is None

    asyncio.run(scenario())


def test_escape_on_menu_quits_panel():
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("escape")
        assert app.result is None

    asyncio.run(scenario())


def test_menu_enter_on_quit_exits():
    status = RouterStatus(host=HOST, reachable=False)

    async def scenario():
        app = PanelApp(status=status, model_ids=[])
        async with app.run_test() as pilot:
            await pilot.press("down", "down", "down", "enter")
        assert app.result is None

    asyncio.run(scenario())
