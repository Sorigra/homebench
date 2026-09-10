"""Guided BIOS panel — plan, doctor, history, then hand off to cmd_run."""

from __future__ import annotations

from typing import List, Optional, Set

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Footer, Label, RadioButton, RadioSet, Static

from ..config import HomebenchConfig, load, save
from ..ops import RouterStatus, router_status
from ..plan import DEPTH_CHOICES, RunPlan

_MSG_NEED_MODEL = "Selecione ao menos um modelo."
_MSG_NEED_DEPTH = "Selecione ao menos uma profundidade."


def format_status_strip(status: RouterStatus) -> str:
    """Render the always-visible router status line (never includes API keys)."""
    if status.reachable:
        residents = ", ".join(status.resident_ids) if status.resident_ids else "nenhum"
        build = status.build_info or "?"
        return (
            f"{status.host} · up · build {build} · residentes: {residents}"
        )
    return f"{status.host} · down"


def discover_model_ids(status: RouterStatus) -> List[str]:
    """Return sorted model ids from the router when reachable."""
    if not status.reachable:
        return []
    from ..lifecycle.router import LlamaRouterClient
    from ..providers.base import ProviderError

    try:
        client = LlamaRouterClient(host=status.host)
        return sorted(m.id for m in client.list_models() if m.id)
    except ProviderError:
        return []


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
    #menu-body, #plan-body {
        padding: 1 2;
        height: 1fr;
    }
    #plan-message {
        color: $warning;
        height: auto;
        min-height: 1;
    }
    .depth-row, .model-row {
        height: auto;
        min-height: 1;
    }
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("q", "quit_panel", "Sair"),
        ("p", "show_plan", "Planejar"),
        ("m", "show_menu", "Menu"),
    ]

    def __init__(
        self,
        status: Optional[RouterStatus] = None,
        *,
        model_ids: Optional[List[str]] = None,
        home: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._status = status
        self._model_ids = model_ids
        self._home = home
        self._result: Optional[RunPlan] = None
        self._current_plan = RunPlan(model_ids=[], depths=[])

    @property
    def result(self) -> Optional[RunPlan]:
        return self._result

    def compose(self) -> ComposeResult:
        yield Static(id="status-strip")
        with Vertical(id="menu-view"):
            yield Static(
                "Menu principal\n\n"
                "[p] Planejar   [d] Doctor   [h] Histórico\n"
                "[q] Sair",
                id="menu-body",
            )
        with Vertical(id="plan-view", classes="hidden"):
            yield Label("Planejar", id="plan-title")
            yield Vertical(id="model-list")
            yield Label("Profundidades:")
            with Horizontal(classes="depth-row"):
                for depth in DEPTH_CHOICES:
                    yield Checkbox(str(depth), id=f"depth-{depth}")
            yield Label("Tipo de teste:")
            with RadioSet(id="test-type"):
                yield RadioButton("Só velocidade", id="type-speed", value=True)
                yield RadioButton("Só qualidade", id="type-quality")
                yield RadioButton("Velocidade e qualidade", id="type-both")
            yield Static("", id="plan-message")
            yield Button("Rodar", id="run-btn", variant="primary")
            yield Static("[m] Menu   [q] Sair", id="plan-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_status_strip()
        if self._model_ids is None:
            if self._status is None:
                self._status = router_status()
            self._model_ids = discover_model_ids(self._status)
        self._build_model_checkboxes()
        self._restore_last_plan()

    def _build_model_checkboxes(self) -> None:
        container = self.query_one("#model-list")
        container.remove_children()
        for model_id in self._model_ids or []:
            container.mount(Checkbox(model_id, id=f"model-{model_id}"))

    def _restore_last_plan(self) -> None:
        cfg = load(self._home)
        if not cfg.last_plan:
            return
        restored = RunPlan.restore(cfg.last_plan, self._model_ids or [])
        self._apply_plan_to_ui(restored)

    def _apply_plan_to_ui(self, plan: RunPlan) -> None:
        self._current_plan = plan
        for model_id in self._model_ids or []:
            cb = self.query_one(f"#model-{model_id}", Checkbox)
            cb.value = model_id in plan.model_ids
        for depth in DEPTH_CHOICES:
            self.query_one(f"#depth-{depth}", Checkbox).value = depth in plan.depths
        radio = self.query_one("#test-type", RadioSet)
        if plan.run_speed and plan.run_quality:
            radio.pressed = self.query_one("#type-both", RadioButton)
        elif plan.run_quality:
            radio.pressed = self.query_one("#type-quality", RadioButton)
        else:
            radio.pressed = self.query_one("#type-speed", RadioButton)

    def _read_plan_from_ui(self) -> RunPlan:
        model_ids = [
            mid for mid in (self._model_ids or [])
            if self.query_one(f"#model-{mid}", Checkbox).value
        ]
        depths = [d for d in DEPTH_CHOICES if self.query_one(f"#depth-{d}", Checkbox).value]
        test_type = self.query_one("#test-type", RadioSet).pressed_button
        run_speed = True
        run_quality = False
        if test_type is not None:
            if test_type.id == "type-quality":
                run_speed, run_quality = False, True
            elif test_type.id == "type-both":
                run_speed, run_quality = True, True
        return RunPlan(model_ids=model_ids, depths=depths,
                       run_speed=run_speed, run_quality=run_quality)

    def _save_last_plan(self, plan: RunPlan) -> None:
        cfg = load(self._home)
        cfg.last_plan = plan.to_dict()
        save(cfg, self._home)

    def refresh_status_strip(self) -> None:
        if self._status is None:
            self._status = router_status()
        self.query_one("#status-strip", Static).update(
            format_status_strip(self._status)
        )

    def _show_view(self, name: str) -> None:
        menu = self.query_one("#menu-view")
        plan = self.query_one("#plan-view")
        if name == "menu":
            menu.remove_class("hidden")
            plan.add_class("hidden")
        else:
            menu.add_class("hidden")
            plan.remove_class("hidden")

    def action_show_menu(self) -> None:
        self._show_view("menu")

    def action_show_plan(self) -> None:
        self._show_view("plan")

    def action_quit_panel(self) -> None:
        self.exit(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self._try_run()

    def _try_run(self) -> None:
        plan = self._read_plan_from_ui()
        problems = plan.problems()
        msg = self.query_one("#plan-message", Static)
        if problems:
            if not plan.model_ids:
                msg.update(_MSG_NEED_MODEL)
            elif not plan.depths:
                msg.update(_MSG_NEED_DEPTH)
            else:
                msg.update(problems[0])
            return
        msg.update("")
        self._current_plan = plan
        self._save_last_plan(plan)


def run_panel(
    status: Optional[RouterStatus] = None,
    *,
    home: Optional[str] = None,
) -> Optional[RunPlan]:
    """Open the panel; return a confirmed ``RunPlan`` or ``None`` if the user quit."""
    app = PanelApp(status=status, home=home)
    app.run()
    return app.result
