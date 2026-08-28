"""`homebench models` — router inspection (MLC-10).

Also guards the coupling between the registered subparsers and ``_COMMANDS``:
a subcommand missing from that set silently becomes ``homebench run <name>``
(design.md, Risks & Concerns).
"""

import argparse
import io

import httpx
import pytest
from rich.console import Console

from homebench import cli

HOST = "http://router.test"

PROPS = {"role": "router", "max_instances": 2, "models_autoload": False,
         "build_info": "b10615-f280b2698"}


def _console():
    return Console(file=io.StringIO(), width=200, force_terminal=False)


def _out(console):
    return console.file.getvalue()


def _args(argv):
    return cli.build_parser().parse_args(cli._inject_default_command(argv))


def _entry(model_id, value, args, source="models_dir"):
    return {"id": model_id, "source": source,
            "status": {"value": value, "args": args, "preset": model_id}}


MODELS = {"data": [
    _entry("qwen35-4b", "loaded",
           ["/app/llama-server", "-m", "/models/qwen35-4b.gguf", "-ngl", "99"]),
    _entry("qwen35-14b", "loading",
           ["/app/llama-server", "-m", "/models/qwen35-14b.gguf", "-ngl", "77"]),
    _entry("gpt-oss-120b", "unloaded",
           ["/app/llama-server", "-m", "/models/gpt-oss.gguf", "-ngl", "12"],
           source="preset"),
]}


# =====================================================================
# listing
# =====================================================================
def test_models_lists_every_model_with_its_state(httpx_mock, monkeypatch):
    monkeypatch.setenv("LLAMACPP_HOST", HOST)
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=MODELS)
    console = _console()

    assert cli.cmd_models(_args(["models"]), console) == 0

    out = _out(console)
    for name in ("qwen35-4b", "qwen35-14b", "gpt-oss-120b"):
        assert name in out
    for state in ("loaded", "loading", "unloaded"):
        assert state in out


def test_resident_models_show_their_effective_parameters(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=MODELS)
    console = _console()

    cli.cmd_models(_args(["models", "--host", HOST]), console)

    out = _out(console)
    assert "-ngl 99" in out                       # the resident model's argv
    assert "-ngl 12" not in out                   # an unloaded model has none in effect
    assert "b10615-f280b2698" in out              # which build produced these numbers


def test_models_reports_how_many_are_resident(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json=PROPS)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=MODELS)
    console = _console()

    cli.cmd_models(_args(["models", "--host", HOST]), console)

    assert "3 model(s) · 1 resident" in _out(console)


# =====================================================================
# failure paths: an error line, never a traceback
# =====================================================================
def test_unreachable_router_reports_the_host_without_a_stack_trace(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    console = _console()

    assert cli.cmd_models(_args(["models", "--host", HOST]), console) == 1

    out = _out(console)
    assert HOST in out and "error:" in out
    assert "Traceback" not in out


def test_rejected_key_reports_an_error_without_echoing_the_key(httpx_mock, monkeypatch):
    monkeypatch.setenv("LLAMACPP_API_KEY", "sk-super-secret")
    httpx_mock.add_response(url=f"{HOST}/props", status_code=401)
    console = _console()

    assert cli.cmd_models(_args(["models", "--host", HOST]), console) == 1

    out = _out(console)
    assert "sk-super-secret" not in out
    assert "Traceback" not in out


def test_non_router_host_says_so_instead_of_listing_fake_state(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/props", json={"model_path": "/m.gguf"})
    httpx_mock.add_response(url=f"{HOST}/v1/models", json=MODELS)
    console = _console()

    assert cli.cmd_models(_args(["models", "--host", HOST]), console) == 1
    assert "not a llama.cpp router" in _out(console)


def test_other_providers_are_rejected_with_an_explanation():
    console = _console()
    assert cli.cmd_models(_args(["models", "--provider", "ollama"]), console) == 1
    assert "llama.cpp router" in _out(console)


# =====================================================================
# _COMMANDS must stay in step with the registered subparsers
# =====================================================================
def _registered_subcommands():
    parser = cli.build_parser()
    actions = [a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction)]
    assert len(actions) == 1
    return set(actions[0].choices)


def test_models_is_a_registered_subcommand():
    assert "models" in _registered_subcommands()
    assert "models" in cli._COMMANDS


def test_commands_set_matches_the_registered_subparsers():
    assert _registered_subcommands() == cli._COMMANDS


@pytest.mark.parametrize("name", sorted(_registered_subcommands()))
def test_every_subcommand_survives_default_injection(name):
    # a name missing from _COMMANDS would come back as ["run", name]
    assert cli._inject_default_command([name]) == [name]


@pytest.mark.parametrize("name", sorted(_registered_subcommands()))
def test_every_subcommand_parses_to_its_own_command(name):
    args = cli.build_parser().parse_args(cli._inject_default_command([name]))
    assert args.command == name
