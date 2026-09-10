import asyncio
from pathlib import Path

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
