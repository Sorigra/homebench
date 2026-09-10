import asyncio
import json
import os
from pathlib import Path

from textual.widgets import Static

from homebench.config import HomebenchConfig, load, save
from homebench.ops import RouterStatus
from homebench.tui.panel import PanelApp, format_status_strip, run_panel

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


def test_plan_screen_two_models_in_plan(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    status = RouterStatus(host=HOST, reachable=True, build_info="b1")
    model_ids = ["alpha", "beta"]

    async def scenario():
        app = PanelApp(status=status, model_ids=model_ids, home=home)
        async with app.run_test() as pilot:
            await _open_plan(app, pilot)
            await pilot.click(f"#model-alpha")
            await pilot.click(f"#model-beta")
            await pilot.click("#depth-0")
            plan = app._read_plan_from_ui()
            assert plan.model_ids == ["alpha", "beta"]
            assert plan.depths == [0]

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
            await pilot.click("#model-alpha")
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
            await pilot.click("#model-alpha")
            await pilot.click("#model-beta")
            await pilot.click("#depth-0")
            await pilot.click("#run-btn")
            await pilot.pause(0.05)

    asyncio.run(scenario())
    cfg = load(home=home)
    assert cfg.last_plan is not None
    assert cfg.last_plan["model_ids"] == ["alpha", "beta"]
    assert cfg.last_plan["depths"] == [0]


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
