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
