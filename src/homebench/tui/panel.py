"""Guided BIOS panel — plan, doctor, history, then hand off to cmd_run."""

from __future__ import annotations

from typing import Optional

from textual.app import App, ComposeResult
from textual.widgets import Footer, Static

from ..ops import RouterStatus, router_status
from ..plan import RunPlan


def format_status_strip(status: RouterStatus) -> str:
    """Render the always-visible router status line (never includes API keys)."""
    if status.reachable:
        residents = ", ".join(status.resident_ids) if status.resident_ids else "nenhum"
        build = status.build_info or "?"
        return (
            f"{status.host} · up · build {build} · residentes: {residents}"
        )
    return f"{status.host} · down"


class PanelApp(App):
    """Textual BIOS-style panel with a permanent status strip."""

    TITLE = "homebench"
    SUB_TITLE = "painel"

    CSS = """
    #status-strip {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
    }
    #menu-body {
        padding: 1 2;
    }
    """

    BINDINGS = [
        ("q", "quit_panel", "Sair"),
    ]

    def __init__(self, status: Optional[RouterStatus] = None) -> None:
        super().__init__()
        self._status = status
        self._result: Optional[RunPlan] = None

    @property
    def result(self) -> Optional[RunPlan]:
        return self._result

    def compose(self) -> ComposeResult:
        yield Static(id="status-strip")
        yield Static(
            "Menu principal — Planejar, Doctor, Histórico (em breve)",
            id="menu-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_status_strip()

    def refresh_status_strip(self) -> None:
        if self._status is None:
            self._status = router_status()
        self.query_one("#status-strip", Static).update(
            format_status_strip(self._status)
        )

    def action_quit_panel(self) -> None:
        self.exit(None)


def run_panel(status: Optional[RouterStatus] = None) -> Optional[RunPlan]:
    """Open the panel; return a confirmed ``RunPlan`` or ``None`` if the user quit."""
    app = PanelApp(status=status)
    app.run()
    return app.result
