"""The CLI's guarded unload flow (MLC-08).

Nothing is unloaded without either an answered confirmation or
``--force-unload``, and a refusal stops the run before any benchmark.
"""

import io

import pytest
from rich.console import Console

from homebench import cli
from homebench.models import ModelInfo
from homebench.providers.base import ProviderError
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
# _prepare_router_models -> (proceed, prepare_hook)
# =====================================================================
def _router_provider(*states):
    return FakeRouterProvider(FakeRouter(list(states), allow_mutations=True))


def _mi(name):
    return ModelInfo(name, "llamacpp")


def test_non_router_provider_is_left_alone():
    proceed, hook = cli._prepare_router_models(
        PlainProvider(), [ModelInfo("m", "ollama")], _args(argv=[]), _console())
    assert proceed is True
    assert hook is None


def test_no_confirmation_when_nothing_foreign_is_resident(monkeypatch):
    # only the models this run measures are resident -> nothing to approve
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("must not ask"))
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    provider = _router_provider(_state("target", "loaded"))

    proceed, hook = cli._prepare_router_models(
        provider, [_mi("target")], _args(argv=[]), _console())

    assert proceed is True and callable(hook)


def test_refusal_of_a_foreign_resident_unloads_nothing_and_stops_the_run(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    provider = _router_provider(_state("target", "unloaded"),
                                _state("resident", "loaded"))
    console = _console()

    proceed, hook = cli._prepare_router_models(
        provider, [_mi("target")], _args(argv=[]), console)

    assert proceed is False and hook is None
    assert [c[0] for c in provider._client.calls] == ["list_models"]
    assert "aborted" in _out(console)


def test_hook_makes_each_model_the_sole_resident_and_reports_its_args(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("m1", "unloaded"), _state("m2", "unloaded"),
                                _state("m3", "unloaded"), _state("resident", "loaded"))

    proceed, hook = cli._prepare_router_models(
        provider, [_mi("m1"), _mi("m2"), _mi("m3")],
        _args(argv=["--force-unload"]), _console())
    assert proceed is True

    # the Runner calls the hook once per model, in turn
    seen_args = {m: hook(_mi(m)) for m in ("m1", "m2", "m3")}

    client = provider._client
    loaded = [c[1] for c in client.calls if c[0] == "load"]
    assert loaded == ["m1", "m2", "m3"]                 # every model, not just the first
    assert "resident" in [c[1] for c in client.calls if c[0] == "unload"]
    # only the last model stays resident
    assert [s.id for s in client._states if s.status == "loaded"] == ["m3"]
    assert seen_args["m2"] == ["/app/llama-server", "-m", "/models/m2.gguf"]


def test_each_model_is_resolved_and_loaded_with_its_own_override(monkeypatch, tmp_path):
    # the per-model closure must key off the model it is handed, not models[0]
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    (tmp_path / "load-params.json").write_text(
        '{"m1": ["-ngl", "10"], "m2": ["-ngl", "20"]}')
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("m1", "unloaded", ["-ngl", "99"]),
                                _state("m2", "unloaded", ["-ngl", "99"]))

    _, hook = cli._prepare_router_models(
        provider, [_mi("m1"), _mi("m2")], _args(argv=["--force-unload"]), _console())
    hook(_mi("m1"))
    hook(_mi("m2"))

    loads = {c[1]: c[2] for c in provider._client.calls if c[0] == "load"}
    assert loads == {"m1": ["-ngl", "10"], "m2": ["-ngl", "20"]}


def test_a_model_that_becomes_resident_mid_run_is_not_unloaded_silently(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("m1", "unloaded"), _state("m2", "unloaded"))

    _, hook = cli._prepare_router_models(
        provider, [_mi("m1"), _mi("m2")], _args(argv=["--force-unload"]), _console())
    hook(_mi("m1"))
    provider._client._states.append(_state("intruder", "loaded"))   # a third party

    with pytest.raises(ProviderError) as exc:
        hook(_mi("m2"))
    assert "intruder" in str(exc.value)
    assert "intruder" in [s.id for s in provider._client._states if s.status == "loaded"]


def test_server_resolved_preset_is_not_echoed_back_as_extra_args(monkeypatch):
    # the router already resolved this argv; sending it back would duplicate it
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("target", "unloaded", ["-ngl", "99"]))

    _, hook = cli._prepare_router_models(provider, [_mi("target")],
                                         _args(argv=["--force-unload"]), _console())
    hook(_mi("target"))

    load = next(c for c in provider._client.calls if c[0] == "load")
    assert load[2] == []


def test_json_override_is_sent_as_extra_args(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBENCH_HOME", str(tmp_path))
    (tmp_path / "load-params.json").write_text('{"target": ["-ngl", "20"]}')
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))
    provider = _router_provider(_state("target", "unloaded", ["-ngl", "99"]))

    _, hook = cli._prepare_router_models(provider, [_mi("target")],
                                         _args(argv=["--force-unload"]), _console())
    hook(_mi("target"))

    load = next(c for c in provider._client.calls if c[0] == "load")
    assert load[2] == ["-ngl", "20"]


# =====================================================================
# cmd_run honours the refusal / wires the hook into the runner
# =====================================================================
def test_cmd_run_returns_nonzero_and_never_benchmarks_on_refusal(monkeypatch):
    provider = _router_provider(_state("target", "unloaded"),
                                _state("resident", "loaded"))
    monkeypatch.setattr(cli, "_resolve_provider", lambda args, console: provider)
    monkeypatch.setattr(cli, "_select_models",
                        lambda p, a, c: [_mi("target")])
    monkeypatch.setattr(cli, "_build_runner",
                        lambda *a, **kw: pytest.fail("no runner may be built"))
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(True))
    monkeypatch.setattr("builtins.input", lambda *a: "n")

    assert cli.cmd_run(_args(argv=[]), _console()) == 1
    assert [c[0] for c in provider._client.calls] == ["list_models"]


class _Stop(Exception):
    pass


def test_cmd_run_hands_the_prepare_hook_to_the_runner(monkeypatch):
    provider = _router_provider(_state("target", "unloaded"))
    captured = {}

    def fake_build(prov, args, prepare_hook=None, depths=None):
        captured["hook"] = prepare_hook
        raise _Stop

    monkeypatch.setattr(cli, "_resolve_provider", lambda args, console: provider)
    monkeypatch.setattr(cli, "_select_models", lambda p, a, c: [_mi("target")])
    monkeypatch.setattr(cli, "_build_runner", fake_build)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))

    with pytest.raises(_Stop):
        cli.cmd_run(_args(argv=["--force-unload"]), _console())
    assert callable(captured["hook"])


# =====================================================================
# --depths flows into the runner / aborts before touching a model (T16)
# =====================================================================
def test_cmd_run_default_depths_is_the_three_point_sweep(monkeypatch):
    provider = _router_provider(_state("target", "unloaded"))
    captured = {}

    def fake_build(prov, args, prepare_hook=None, depths=None):
        captured["depths"] = depths
        raise _Stop

    monkeypatch.setattr(cli, "_resolve_provider", lambda args, console: provider)
    monkeypatch.setattr(cli, "_select_models", lambda p, a, c: [_mi("target")])
    monkeypatch.setattr(cli, "_build_runner", fake_build)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))

    with pytest.raises(_Stop):
        cli.cmd_run(_args(argv=["--force-unload"]), _console())
    assert captured["depths"] == [0, 8192, 32768]


def test_cmd_run_depths_zero_reproduces_the_pre_sweep_behaviour(monkeypatch):
    provider = _router_provider(_state("target", "unloaded"))
    captured = {}

    def fake_build(prov, args, prepare_hook=None, depths=None):
        captured["depths"] = depths
        raise _Stop

    monkeypatch.setattr(cli, "_resolve_provider", lambda args, console: provider)
    monkeypatch.setattr(cli, "_select_models", lambda p, a, c: [_mi("target")])
    monkeypatch.setattr(cli, "_build_runner", fake_build)
    monkeypatch.setattr(cli.sys, "stdin", _Stdin(False))

    with pytest.raises(_Stop):
        cli.cmd_run(_args(argv=["--force-unload", "--depths", "0"]), _console())
    assert captured["depths"] == [0]


def test_cmd_run_invalid_depths_aborts_before_touching_the_provider(monkeypatch):
    monkeypatch.setattr(cli, "_resolve_provider",
                        lambda *a, **kw: pytest.fail("provider must not be touched"))
    monkeypatch.setattr(cli, "_select_models",
                        lambda *a, **kw: pytest.fail("no model may be selected"))
    console = _console()

    assert cli.cmd_run(_args(argv=["--depths", "not-a-number"]), console) == 1
    assert "not-a-number" in _out(console)
