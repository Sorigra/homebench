"""Environment capture, model round-trip, and HTML/Markdown reports."""

from homebench.models import BenchmarkResult
from homebench.report import env_summary, to_html, to_markdown
from homebench.runner import RunConfig, Runner
from tests.fakes import FakeProvider

SAMPLE_ENV = {
    "homebench_version": "0.7.0",
    "hardware": {
        "os": "Darwin", "os_version": "23.3.0", "arch": "arm64",
        "cpu": "Apple M1", "cpu_cores": 8,
        "ram_total_bytes": 16 * 1_000_000_000, "python_version": "3.11.0",
        "gpu": {"name": "Apple Silicon GPU", "vram_bytes": 0, "kind": "apple"},
    },
}


def _real_result():
    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=False, use_cache=False))
    return runner.run(provider.list_models())


# ---- environment capture ---------------------------------------------------
def test_runner_captures_environment():
    result = _real_result()
    env = result.environment
    assert env.get("homebench_version")
    assert "hardware" in env
    assert env["hardware"].get("ram_total_bytes", 0) > 0


def test_env_summary_formats():
    s = env_summary(SAMPLE_ENV)
    assert "Darwin" in s and "arm64" in s
    assert "Apple M1" in s and "×8" in s
    assert "RAM" in s
    assert "homebench 0.7.0" in s
    assert env_summary({}) == ""


# ---- round-trip (from_dict) ------------------------------------------------
def test_benchmark_result_roundtrip():
    result = _real_result()
    restored = BenchmarkResult.from_dict(result.to_dict())
    assert restored.provider == result.provider
    assert len(restored.reports) == len(result.reports)
    a, b = result.reports[0], restored.reports[0]
    assert b.model.name == a.model.name
    assert b.quality_score == a.quality_score          # recomputed from task_results
    assert b.speed.tokens_per_sec == a.speed.tokens_per_sec
    assert restored.environment == result.environment


def test_from_dict_ignores_extra_computed_keys():
    # to_dict adds computed keys (quality_score, tasks_passed) not in __init__
    result = _real_result()
    d = result.to_dict()
    assert "quality_score" in d["reports"][0]          # computed extra
    BenchmarkResult.from_dict(d)                        # must not raise


# ---- markdown --------------------------------------------------------------
def test_markdown_includes_environment():
    result = _real_result()
    result.environment = SAMPLE_ENV
    md = to_markdown(result)
    assert "**Environment:**" in md
    assert "Apple M1" in md


# ---- html ------------------------------------------------------------------
def test_html_report_is_self_contained_and_populated():
    result = _real_result()
    result.environment = SAMPLE_ENV
    html = to_html(result)
    assert html.startswith("<!doctype html>")
    assert "<style>" in html and "http" not in html.split("<footer>")[0].replace(
        "https://github.com/david-g-3654/homebench", "")  # no external assets in body
    assert "Leaderboard" in html
    assert "fast:1b" in html and "smart:8b" in html
    assert "Quality by category" in html
    assert "Apple M1" in html                            # env surfaced
    # a couple of CSS bars rendered
    assert html.count('class="fill') >= 2


GIB = 1024 ** 3


def _report_with_peak(name, peak_bytes):
    from homebench.models import (
        MemoryMetrics, ModelInfo, ModelReport, SpeedMetrics, TaskResult,
    )
    r = ModelReport(model=ModelInfo(name, "ollama", size_bytes=2 * GIB,
                                    parameter_size="3B"))
    r.speed = SpeedMetrics(tokens_per_sec=20.0, ttft_s=0.1)
    r.memory = MemoryMetrics(size_bytes=2 * GIB, rss_peak_bytes=peak_bytes)
    r.task_results = [TaskResult("t", "math", 1.0, True)]
    return r


def test_peak_surfaced_in_all_tables():
    from homebench.report import (
        _peak_display, leaderboard_table, to_html, to_markdown,
    )
    res = BenchmarkResult(provider="ollama",
                          reports=[_report_with_peak("m", 3 * GIB)])
    headers = [str(c.header) for c in leaderboard_table(res).columns]
    assert "Peak" in headers and "Memory" in headers

    md = to_markdown(res)
    assert "| Peak |" in md and "3.0 GB" in md

    html = to_html(res)
    assert ">Peak</th>" in html and "3.0 GB" in html

    # resident (Memory) still shown separately; peak "–" when unmeasured
    assert _peak_display(_report_with_peak("x", 0)) == "–"
    assert _peak_display(_report_with_peak("y", 3 * GIB)) == "3.0 GB"


def test_runner_samples_peak_across_run():
    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=True, use_cache=False))
    result = runner.run([provider.list_models()[0]])
    peak = result.reports[0].memory.rss_peak_bytes
    assert isinstance(peak, int) and peak >= 0   # best-effort; 0 if no procs


def test_html_handles_error_rows():
    from homebench.models import ModelInfo, ModelReport
    result = BenchmarkResult(provider="ollama")
    result.reports = [ModelReport(model=ModelInfo("boom", "ollama"), error="kaboom")]
    html = to_html(result)
    assert "kaboom" in html and "error" in html


# =====================================================================
# leaderboard_rows() / Rich table: one row per (model, depth) (PERF-09, PERF-17)
# =====================================================================
import io

from rich.console import Console

from homebench.models import DepthMetrics, ModelInfo, ModelReport, SpeedMetrics


def _render(table):
    console = Console(file=io.StringIO(), width=200, force_terminal=False)
    console.print(table)
    return console.file.getvalue()


def _report_with_depths(name, points, error=None):
    r = ModelReport(model=ModelInfo(name, "llamacpp", size_bytes=2 * GIB,
                                    parameter_size="3B"))
    r.depth_results = points
    if points and points[0].skipped is None:
        # Mirrors the runner's contract: ``speed`` is the shallowest measured
        # depth (PERF-15), set independently of depth_results here so the
        # ranking test below is not tautological with the row expansion.
        p0 = points[0]
        r.speed = SpeedMetrics(tokens_per_sec=p0.decode_tps, ttft_s=p0.ttft_s,
                               prefill_tps=p0.prefill_tps)
    r.error = error
    return r


def test_leaderboard_rows_expands_one_row_per_depth():
    from homebench.report import leaderboard_rows

    points = [
        DepthMetrics(depth_requested=0, depth_actual=22, prefill_tps=2714.0,
                     decode_tps=95.1, ttft_s=0.1),
        DepthMetrics(depth_requested=8192, depth_actual=8190, prefill_tps=2709.0,
                     decode_tps=83.3, ttft_s=1.0),
        DepthMetrics(depth_requested=32768, depth_actual=32001, prefill_tps=1805.0,
                     decode_tps=73.0, ttft_s=4.0),
    ]
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("gemma4-e2b", points)])
    rows = leaderboard_rows(result)
    assert len(rows) == 3
    assert [row.depth for row in rows] == [22, 8190, 32001]
    assert [row.decode_tps for row in rows] == [95.1, 83.3, 73.0]
    assert [row.prefill_tps for row in rows] == [2714.0, 2709.0, 1805.0]
    assert all(row.rank == 1 for row in rows)   # same model, same rank


def test_leaderboard_rows_legacy_report_without_depth_results_is_one_row():
    from homebench.report import leaderboard_rows

    r = ModelReport(model=ModelInfo("legacy", "ollama"))
    r.speed = SpeedMetrics(tokens_per_sec=54.03, ttft_s=0.2)   # depth_results == []
    result = BenchmarkResult(provider="ollama", reports=[r])

    rows = leaderboard_rows(result)
    assert len(rows) == 1
    assert rows[0].point is None
    assert rows[0].depth is None
    assert rows[0].decode_tps == 54.03


def test_leaderboard_table_shows_dash_for_missing_prefill_never_zero():
    from homebench.report import leaderboard_table

    point = DepthMetrics(depth_requested=0, depth_actual=10, prefill_tps=None,
                         decode_tps=54.03, ttft_s=0.129)
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("Ornith-1.5-35B-A3B-Q8", [point])])
    out = _render(leaderboard_table(result))
    assert "54.0" in out           # the real decode rate is shown
    assert "0.00" not in out       # never a fake zero for the missing prefill
    assert "–" in out              # the prefill cell reads as unknown


def test_leaderboard_table_ranks_by_shallowest_depth_decode():
    from homebench.report import leaderboard_table, rank_reports

    # depth_results carries a HIGHER decode at a deeper point than the
    # shallow one -- unrealistic in practice, but it proves ranking reads
    # ``speed`` (contractually the shallowest depth, PERF-15) and not some
    # max/average over the sweep.
    slow_shallow = _report_with_depths("slow-shallow", [
        DepthMetrics(depth_requested=0, depth_actual=10, decode_tps=10.0),
        DepthMetrics(depth_requested=8192, depth_actual=8190, decode_tps=999.0),
    ])
    fast_shallow = _report_with_depths("fast-shallow", [
        DepthMetrics(depth_requested=0, depth_actual=10, decode_tps=100.0),
    ])
    result = BenchmarkResult(provider="llamacpp",
                             reports=[slow_shallow, fast_shallow])
    ranked = rank_reports(result.reports)
    assert [r.model.name for r in ranked] == ["fast-shallow", "slow-shallow"]

    out = _render(leaderboard_table(result))
    assert out.index("fast-shallow") < out.index("slow-shallow")


def test_leaderboard_table_shows_skip_reason_for_a_skipped_depth():
    from homebench.report import leaderboard_table

    reason = "context 32768 exceeds the model's window"
    points = [
        DepthMetrics(depth_requested=0, depth_actual=20, decode_tps=50.0),
        DepthMetrics(depth_requested=32768, skipped=reason),
    ]
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("small-ctx", points)])
    out = _render(leaderboard_table(result))
    assert reason in out


def test_leaderboard_table_has_depth_prefill_decode_columns():
    from homebench.report import leaderboard_table

    result = BenchmarkResult(provider="llamacpp", reports=[])
    headers = [str(c.header) for c in leaderboard_table(result).columns]
    assert "Depth" in headers
    assert "Prefill tok/s" in headers
    assert "Decode tok/s" in headers


# =====================================================================
# Markdown / JSON / HTML exports render the same depth rows (T13, PERF-17)
# =====================================================================
def test_markdown_leaderboard_has_one_row_per_depth_with_new_columns():
    points = [
        DepthMetrics(depth_requested=0, depth_actual=22, prefill_tps=2714.0,
                     decode_tps=95.1, ttft_s=0.1),
        DepthMetrics(depth_requested=8192, depth_actual=8190, prefill_tps=2709.0,
                     decode_tps=83.3, ttft_s=1.0),
        DepthMetrics(depth_requested=32768, depth_actual=32001, prefill_tps=1805.0,
                     decode_tps=73.0, ttft_s=4.0),
    ]
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("gemma4-e2b", points)])
    md = to_markdown(result)
    assert "| # | Model | Params | Quality | Pass | Depth | Prefill tok/s " \
           "| Decode tok/s | TTFT | Memory | Peak | Value |" in md
    # one data row per depth, each carrying its own decode figure
    assert md.count("| 1 | gemma4-e2b |") == 3
    assert "95.1" in md and "83.3" in md and "73.0" in md
    assert "22" in md and "8190" in md and "32001" in md


def test_markdown_leaderboard_shows_dash_for_missing_prefill():
    point = DepthMetrics(depth_requested=0, depth_actual=10, prefill_tps=None,
                         decode_tps=54.03, ttft_s=0.129)
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("Ornith-1.5-35B-A3B-Q8", [point])])
    md = to_markdown(result)
    assert "54.0" in md
    assert "0.00" not in md


def test_html_leaderboard_has_depth_and_prefill_columns_and_decode_bar():
    points = [
        DepthMetrics(depth_requested=0, depth_actual=22, prefill_tps=2714.0,
                     decode_tps=95.1, ttft_s=0.1),
        DepthMetrics(depth_requested=8192, depth_actual=8190, prefill_tps=2709.0,
                     decode_tps=83.3, ttft_s=1.0),
    ]
    result = BenchmarkResult(provider="llamacpp",
                             reports=[_report_with_depths("gemma4-e2b", points)])
    html = to_html(result)
    assert "<th class=\"num\">Depth</th>" in html
    assert "<th class=\"num\">Prefill tok/s</th>" in html
    assert "Decode tok/s</th>" in html
    # two depth rows rendered, each with its own decode bar/value
    assert html.count("<td class=\"model\">gemma4-e2b</td>") == 2
    assert "95.1" in html and "83.3" in html
    # the bar width is calibrated per row by decode_tps, not a single value
    # repeated for the whole model: the faster (shallower) row hits 100%,
    # the slower (deeper) one is proportionally smaller (83.3/95.1 ~= 88%).
    assert "width:100%" in html
    assert "width:88%" in html


def test_to_json_exports_full_depth_results():
    import json

    from homebench.report import to_json

    _, result = _fake_run_with_default_depths()
    data = json.loads(to_json(result))
    rep = data["reports"][0]
    assert "depth_results" in rep
    assert len(rep["depth_results"]) == len(result.reports[0].depth_results) > 0
    first = rep["depth_results"][0]
    assert set(first) == {
        "depth_requested", "depth_actual", "prefill_tps", "decode_tps",
        "ttft_s", "prompt_eval_s", "output_tokens", "cache_hit_tokens", "skipped",
    }


def _fake_run_with_default_depths():
    from homebench.runner import RunConfig, Runner

    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=False, use_cache=False,
                                        run_quality=False))
    return provider, runner.run(provider.list_models())


# =====================================================================
# plainui live table: depth/prefill/decode columns + depth in Status (T14)
# =====================================================================
def test_plainui_live_table_has_depth_prefill_decode_columns():
    from homebench.plainui import PlainReporter

    reporter = PlainReporter([ModelInfo("fast:1b", "ollama")], total_tasks=0)
    headers = [str(c.header) for c in reporter.render().renderables[1].columns]
    assert "Depth" in headers
    assert "Prefill tok/s" in headers
    assert "Decode tok/s" in headers
    assert "tok/s" not in headers


def test_plainui_status_shows_the_current_depth_during_the_speed_phase():
    from homebench.plainui import PlainReporter
    from homebench.runner import EV_PHASE

    reporter = PlainReporter([ModelInfo("fast:1b", "ollama")], total_tasks=0)
    reporter(EV_PHASE, model="fast:1b", phase="speed", depth=8192)
    text = reporter._status_text("fast:1b")
    assert "8192" in str(text)
    assert "speed" in str(text)


def test_plainui_final_leaderboard_prints_one_line_per_measured_depth():
    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=False, use_cache=False,
                                        run_quality=False,
                                        depths=[0, 8192, 32768]))
    console = Console(file=io.StringIO(), width=200, force_terminal=False)

    from homebench.plainui import run_plain

    run_plain(runner, provider.list_models(), console)
    out = console.file.getvalue()
    assert out.count("fast:1b") >= 3   # one row per depth in the final table
