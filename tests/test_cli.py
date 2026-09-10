from homebench.cli import _COMMANDS, _inject_default_command, build_parser


def test_inject_default_command():
    assert _inject_default_command([], stdin_is_tty=False, stdout_is_tty=False) == ["run"]
    assert _inject_default_command([], stdin_is_tty=True, stdout_is_tty=True) == ["panel"]
    assert _inject_default_command(["--no-tui"]) == ["run", "--no-tui"]
    assert _inject_default_command(["-m", "x"]) == ["run", "-m", "x"]
    # explicit subcommands are left untouched
    assert _inject_default_command(["list"]) == ["list"]
    assert _inject_default_command(["doctor"]) == ["doctor"]
    assert _inject_default_command(["run", "--no-tui"]) == ["run", "--no-tui"]
    assert _inject_default_command(["run", "--limit", "2"]) == ["run", "--limit", "2"]
    # global help/version bypass the default
    assert _inject_default_command(["--version"]) == ["--version"]
    assert "panel" in _COMMANDS


def test_provider_flag_reaches_list_command():
    parser = build_parser()
    args = parser.parse_args(["list", "--provider", "lmstudio"])
    assert args.command == "list"
    assert args.provider == "lmstudio"


def test_run_flags_parse():
    parser = build_parser()
    args = parser.parse_args(_inject_default_command(
        ["--provider", "lmstudio", "--no-tui", "--limit", "3", "--judge", "m"]
    ))
    assert args.command == "run"
    assert args.provider == "lmstudio"
    assert args.no_tui is True
    assert args.limit == 3
    assert args.judge == "m"


# =====================================================================
# --depths flag (T16, PERF-11)
# =====================================================================
def test_depths_flag_defaults_to_the_three_point_sweep():
    parser = build_parser()
    args = parser.parse_args(_inject_default_command([], stdin_is_tty=False, stdout_is_tty=False))
    assert args.depths == "0,8192,32768"


def test_depths_flag_accepts_a_custom_value():
    parser = build_parser()
    args = parser.parse_args(_inject_default_command(["--depths", "0,4096"]))
    assert args.depths == "0,4096"


def test_depths_flag_is_documented_in_help():
    # top-level --help does not expand subcommand options; check the run
    # subparser's own help instead.
    assert "--depths" in _run_subparser_help()


def _run_subparser_help() -> str:
    import io
    import contextlib

    parser = build_parser()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            parser.parse_args(["run", "--help"])
        except SystemExit:
            pass
    return buf.getvalue()
