"""The CLI's guarded unload flow (MLC-08).

Nothing is unloaded without either an answered confirmation or
``--force-unload``, and a refusal stops the run before any benchmark.
"""

import io

import pytest
from rich.console import Console

from homebench import cli
from homebench.models import ModelInfo
from tests.test_lifecycle_manager import FakeRouter, _state


def _console():
    return Console(file=io.StringIO(), width=100, force_terminal=False)


def _out(console):
    return console.file.getvalue()


def _args(**kw):
    parser = cli.build_parser()
    argv = cli._inject_default_command(list(kw.pop("argv", [])))
    return parser.parse_args(argv)


class _Stdin:
    def __init__(self, interactive):
        self._interactive = interactive

    def isatty(self):
        return self._interactive


class FakeRouterProvider:
    """A llamacpp-like provider whose host is a router."""

    name = "llamacpp"

    def __init__(self, client):
        self._client = client

    def router(self):
        return self._client


class PlainProvider:
    name = "ollama"


def _plan_with(*victims):
    from homebench.lifecycle.models import LifecyclePlan

    return LifecyclePlan(target="target", to_unload=list(victims), reason="because")


# =====================================================================
# --force-unload flag
# =====================================================================
def test_force_unload_flag_parses_on_run():
    assert _args(argv=["--force-unload"]).force_unload is True
    assert _args(argv=["run", "-m", "x"]).force_unload is False


def test_force_unload_skips_the_question(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("must not ask"))
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    console = _console()

    confirm = cli._make_confirmer(_args(argv=["--force-unload"]), console)

    assert confirm(_plan_with("resident-a")) is True
    assert "resident-a" in _out(console)   # still says what it is unloading


# =====================================================================
# interactive confirmation
# =====================================================================
def test_confirmation_lists_the_models_before_asking(monkeypatch):
    console = _console()
    asked_after = {}

    def fake_input(prompt=""):
        asked_after["output"] = _out(console)
        return "y"

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))

    assert cli._make_confirmer(_args(argv=[]), console)(
        _plan_with("resident-a", "resident-b")) is True
    # the names were on screen before the question was asked
    assert "resident-a" in asked_after["output"]
    assert "resident-b" in asked_after["output"]


@pytest.mark.parametrize("answer, expected", [
    ("y", True), ("yes", True), ("Y", True),
    ("n", False), ("", False), ("whatever", False),
])
def test_confirmation_answer_decides(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda *a: answer)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    confirm = cli._make_confirmer(_args(argv=[]), _console())
    assert confirm(_plan_with("resident-a")) is expected


def test_non_interactive_without_the_flag_refuses_and_explains(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("must not ask"))
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    console = _console()

    assert cli._make_confirmer(_args(argv=[]), console)(
        _plan_with("resident-a")) is False
    assert "--force-unload" in _out(console)


# =====================================================================
# _prepare_router_models
# =====================================================================
def _router_provider(*states):
    return FakeRouterProvider(FakeRouter(list(states), allow_mutations=True))


def test_non_router_provider_is_left_alone():
    proceed, params = cli._prepare_router_models(
        PlainProvider(), [ModelInfo("m", "ollama")], _args(argv=[]), _console())
    assert proceed is True
    assert params is None


def test_refusal_unloads_nothing_and_stops_the_run(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    provider = _router_provider(_state("target", "unloaded"),
                                _state("resident", "loaded"))
    console = _console()

    proceed, params = cli._prepare_router_models(
        provider, [ModelInfo("target", "llamacpp")], _args(argv=[]), console)

    assert proceed is False and params is None
    assert "unload" not in [c[0] for c in provider._client.calls]
    assert "load" not in [c[0] for c in provider._client.calls]
    assert "aborted" in _out(console)


def test_approval_unloads_the_others_and_returns_effective_args(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("target", "unloaded"),
                                _state("resident", "loaded"))

    proceed, params = cli._prepare_router_models(
        provider, [ModelInfo("target", "llamacpp")],
        _args(argv=["--force-unload"]), _console())

    assert proceed is True
    assert [c[1] for c in provider._client.calls if c[0] == "unload"] == ["resident"]
    assert params["target"] == ["/app/llama-server", "-m", "/models/target.gguf"]


def test_server_resolved_preset_is_not_echoed_back_as_extra_args(monkeypatch):
    # the router already resolved this argv; sending it back would duplicate it
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("target", "unloaded", ["-ngl", "99"]))

    cli._prepare_router_models(provider, [ModelInfo("target", "llamacpp")],
                               _args(argv=["--force-unload"]), _console())

    load = next(c for c in provider._client.calls if c[0] == "load")
    assert load[2] == []


def test_json_override_is_sent_as_extra_args(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    (tmp_path / "load-params.json").write_text('{"target": ["-ngl", "20"]}')
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("target", "unloaded", ["-ngl", "99"]))

    cli._prepare_router_models(provider, [ModelInfo("target", "llamacpp")],
                               _args(argv=["--force-unload"]), _console())

    load = next(c for c in provider._client.calls if c[0] == "load")
    assert load[2] == ["-ngl", "20"]


# =====================================================================
# cmd_run honours the refusal
# =====================================================================
def test_cmd_run_returns_nonzero_and_never_benchmarks_on_refusal(monkeypatch):
    provider = _router_provider(_state("target", "unloaded"),
                                _state("resident", "loaded"))
    monkeypatch.setattr(cli, "_resolve_provider", lambda args, console: provider)
    monkeypatch.setattr(cli, "_select_models",
                        lambda p, a, c: [ModelInfo("target", "llamacpp")])
    monkeypatch.setattr(cli, "_build_runner",
                        lambda *a, **kw: pytest.fail("no runner may be built"))
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    monkeypatch.setattr("builtins.input", lambda *a: "n")

    assert cli.cmd_run(_args(argv=[]), _console()) == 1
    assert [c[0] for c in provider._client.calls] == ["list_models", "list_models"]
