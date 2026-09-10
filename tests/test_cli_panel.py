import os

from rich.console import Console

from homebench import cli
from homebench.config import HOST_ENV, HomebenchConfig, save


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
