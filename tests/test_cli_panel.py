import io
import os

import pytest
from rich.console import Console

from homebench import cli
from homebench.config import HOST_ENV, HomebenchConfig, save
from homebench.plan import RunPlan
from tests.fakes import FakeProvider


def test_build_parser_accepts_panel_subcommand():
    parser = cli.build_parser()
    args = parser.parse_args(["panel"])
    assert args.command == "panel"


def test_cmd_panel_without_tty_exits_nonzero(capsys):
    console = Console()
    code = cli.cmd_panel(object(), console, stdin_is_tty=False, stdout_is_tty=False)
    assert code != 0
    captured = capsys.readouterr()
    assert "terminal" in captured.out.lower() or "terminal" in captured.err.lower()


def _panel_console():
    return Console(file=io.StringIO(), width=100, force_terminal=False)


def test_cmd_panel_none_skips_cmd_run(monkeypatch):
    monkeypatch.setattr("homebench.tui.panel.run_panel", lambda: None)
    calls = []
    monkeypatch.setattr(cli, "cmd_run", lambda *a, **k: calls.append(1) or 0)
    code = cli.cmd_panel(object(), _panel_console(),
                         stdin_is_tty=True, stdout_is_tty=True)
    assert code == 0
    assert calls == []


def test_cmd_panel_speed_plan_builds_force_unload_namespace(monkeypatch):
    plan = RunPlan(
        model_ids=["alpha", "beta"],
        depths=[0, 8192],
        run_speed=True,
        run_quality=False,
    )
    monkeypatch.setattr("homebench.tui.panel.run_panel", lambda: plan)
    captured = {}

    def fake_cmd_run(args, console):
        captured["args"] = args
        return 0

    monkeypatch.setattr(cli, "cmd_run", fake_cmd_run)
    code = cli.cmd_panel(object(), _panel_console(),
                         stdin_is_tty=True, stdout_is_tty=True)
    assert code == 0
    args = captured["args"]
    assert args.force_unload is True
    assert args.no_quality is True
    assert args.no_speed is False
    assert args.models == "alpha,beta"
    assert args.depths == "0,8192"
    assert args.no_tui is True


def test_cmd_panel_hands_plan_to_cmd_run_with_fake_provider(monkeypatch):
    plan = RunPlan(model_ids=["fast:1b"], depths=[0], run_speed=True)
    monkeypatch.setattr("homebench.tui.panel.run_panel", lambda: plan)
    monkeypatch.setattr(cli, "_resolve_provider",
                        lambda args, console: FakeProvider())
    monkeypatch.setattr(cli, "_prepare_router_models",
                        lambda *a, **k: (True, None))

    class _Stop(Exception):
        pass

    def fake_build(*a, **kw):
        raise _Stop

    monkeypatch.setattr(cli, "_build_runner", fake_build)
    with pytest.raises(_Stop):
        cli.cmd_panel(object(), _panel_console(),
                      stdin_is_tty=True, stdout_is_tty=True)


def test_main_applies_config_to_empty_env(monkeypatch, tmp_path):
    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    saved_host = os.environ.get(HOST_ENV)
    monkeypatch.delenv(HOST_ENV, raising=False)
    save(HomebenchConfig(host="http://192.168.1.5:8080"))
    assert os.environ.get(HOST_ENV) is None
    try:
        code = cli.main(["doctor"])
        assert code in (0, 1)
        assert os.environ.get(HOST_ENV) == "http://192.168.1.5:8080"
    finally:
        if saved_host is None:
            os.environ.pop(HOST_ENV, None)
        else:
            os.environ[HOST_ENV] = saved_host
