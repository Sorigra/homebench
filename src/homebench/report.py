"""Rendering & export: a Rich leaderboard table, plus Markdown / JSON output."""

from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from rich.table import Table

from .models import BenchmarkResult, DepthMetrics, ModelReport


# ---- formatting helpers ----------------------------------------------------
def fmt_bytes(n: int) -> str:
    if not n:
        return "–"
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{x:.0f} {unit}" if unit in ("B", "KB") else f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} TB"


def fmt_tps(v: float) -> str:
    return f"{v:.1f}" if v else "–"


def fmt_ttft(v: float) -> str:
    if not v:
        return "–"
    return f"{v * 1000:.0f} ms" if v < 1 else f"{v:.2f} s"


def fmt_quality(v: Optional[float]) -> str:
    return f"{v:.0f}%" if v is not None else "–"


def _memory_display(r: ModelReport) -> str:
    # Prefer the provider's resident-model size; fall back to on-disk size.
    n = r.memory.size_bytes or r.model.size_bytes
    return fmt_bytes(n)


def _peak_display(r: ModelReport) -> str:
    # Peak resident-set growth of the backend during the whole run (best-effort).
    n = r.memory.rss_peak_bytes
    return fmt_bytes(n) if n else "–"


# ---- environment -----------------------------------------------------------
def _hw(env: dict) -> dict:
    return (env or {}).get("hardware", {}) or {}


def env_summary(env: dict) -> str:
    """One-line host summary from a captured environment dict."""
    hw = _hw(env)
    parts: List[str] = []
    if hw.get("os"):
        os_part = f"{hw['os']} {hw.get('os_version', '')}".strip()
        if hw.get("arch"):
            os_part += f" ({hw['arch']})"
        parts.append(os_part)
    if hw.get("cpu"):
        cpu = hw["cpu"]
        if hw.get("cpu_cores"):
            cpu += f" ×{hw['cpu_cores']}"
        parts.append(cpu)
    if hw.get("ram_total_bytes"):
        parts.append(f"{fmt_bytes(hw['ram_total_bytes'])} RAM")
    gpu = hw.get("gpu") or {}
    if gpu.get("kind") == "nvidia" and gpu.get("vram_bytes"):
        parts.append(f"{gpu.get('name', 'GPU')} {fmt_bytes(gpu['vram_bytes'])}")
    elif gpu.get("kind") == "apple":
        parts.append("Apple GPU (unified)")
    if (env or {}).get("homebench_version"):
        parts.append(f"homebench {env['homebench_version']}")
    if hw.get("python_version"):
        parts.append(f"Python {hw['python_version']}")
    return " · ".join(parts)


# ---- ranking ---------------------------------------------------------------
def rank_reports(reports: List[ModelReport]) -> List[ModelReport]:
    """Rank by quality first, then throughput. Errored models sink to the end.

    ``r.speed`` is contractually the shallowest measured context depth
    (PERF-15), so this also ranks by "decode at the smallest depth" per the
    spec's P3 AC8 without needing to know about depths here.
    """

    def key(r: ModelReport):
        q = r.quality_score if r.quality_score is not None else -1
        return (r.error is not None, -q, -r.speed.tokens_per_sec)

    return sorted(reports, key=key)


# ---- leaderboard rows: one per (model, depth) -------------------------------
@dataclass
class LeaderboardRow:
    """One leaderboard line: a model at one measured context depth.

    ``point`` is ``None`` for a report with no ``depth_results`` -- an error,
    or a run saved before the depth sweep existed (PERF-16 AC2). The derived
    properties then fall back to ``report.speed``, the single pre-sweep
    measurement, so callers never need to branch on which shape they got.
    """

    rank: int
    report: ModelReport
    point: Optional[DepthMetrics] = None

    @property
    def depth(self) -> Optional[int]:
        """Depth actually measured (or requested, if skipped); ``None`` with no sweep."""
        if self.point is None:
            return None
        return self.point.depth_requested if self.point.skipped else self.point.depth_actual

    @property
    def skipped(self) -> Optional[str]:
        return self.point.skipped if self.point is not None else None

    @property
    def prefill_tps(self) -> Optional[float]:
        if self.point is None:
            return self.report.speed.prefill_tps
        return self.point.prefill_tps

    @property
    def decode_tps(self) -> float:
        if self.point is None:
            return self.report.speed.tokens_per_sec
        return self.point.decode_tps

    @property
    def ttft_s(self) -> float:
        if self.point is None:
            return self.report.speed.ttft_s
        return self.point.ttft_s


def leaderboard_rows(result: BenchmarkResult) -> List[LeaderboardRow]:
    """Expand each report into one row per measured depth, in rank order.

    A model with ``depth_results`` becomes one row per point, in the order
    they were measured. A model with none (error, or a legacy run) becomes
    exactly one row with ``point=None`` (PERF-16 AC2). The single shared
    helper keeps the terminal table, the Markdown/JSON/HTML exports, and the
    live renderers from diverging on what a "row" means (PERF-17 AC4).
    """
    rows: List[LeaderboardRow] = []
    for i, r in enumerate(rank_reports(result.reports), start=1):
        if r.depth_results:
            for point in r.depth_results:
                rows.append(LeaderboardRow(rank=i, report=r, point=point))
        else:
            rows.append(LeaderboardRow(rank=i, report=r, point=None))
    return rows


def _depth_cell(row: LeaderboardRow) -> str:
    return "–" if row.point is None else str(row.depth)


def _prefill_cell(row: LeaderboardRow) -> str:
    if row.skipped:
        return "–"
    return fmt_tps(row.prefill_tps)


def _decode_cell(row: LeaderboardRow, *, include_skip_reason: bool = True) -> str:
    if row.skipped:
        return f"skipped: {row.skipped}" if include_skip_reason else "skipped"
    return fmt_tps(row.decode_tps)


# ---- Rich table (shared by CLI + TUI) --------------------------------------
def leaderboard_table(result: BenchmarkResult, title: str = "homebench") -> Table:
    table = Table(title=title, expand=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Model", style="bold")
    table.add_column("Params", justify="right")
    table.add_column("Quality", justify="right")
    table.add_column("Pass", justify="right")
    table.add_column("Depth", justify="right")
    table.add_column("Prefill tok/s", justify="right")
    table.add_column("Decode tok/s", justify="right", style="green")
    table.add_column("TTFT", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Peak", justify="right", style="dim")

    for row in leaderboard_rows(result):
        r = row.report
        if r.error:
            table.add_row(
                str(row.rank), r.model.name, r.model.parameter_size or "–",
                "[red]error[/red]", "–", "–", "–", "–", "–", "–", "–",
            )
            continue
        passed = f"{r.tasks_passed}/{len(r.task_results)}" if r.task_results else "–"
        table.add_row(
            str(row.rank),
            r.model.name,
            r.model.parameter_size or "–",
            fmt_quality(r.quality_score),
            passed,
            _depth_cell(row),
            _prefill_cell(row),
            _decode_cell(row),
            fmt_ttft(row.ttft_s),
            _memory_display(r),
            _peak_display(r),
        )
    return table


# ---- Markdown --------------------------------------------------------------
def to_markdown(result: BenchmarkResult) -> str:
    started = datetime.fromtimestamp(result.started_at).strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("# homebench results")
    lines.append("")
    lines.append(f"- **Provider:** {result.provider}")
    lines.append(f"- **Run at:** {started}")
    lines.append(f"- **Models:** {len(result.reports)}")
    env = env_summary(result.environment)
    if env:
        lines.append(f"- **Environment:** {env}")
    cfg = result.config or {}
    if cfg.get("judge_model"):
        lines.append(f"- **Judge:** {cfg['judge_model']}")
    lines.append("")
    from .score import value_scores, value_verdict

    verdict = value_verdict(result.reports)
    if verdict:
        lines.append(f"> 🏆 **Best value for your laptop:** {verdict}")
        lines.append("")

    scores = value_scores(result.reports)
    lines.append("## Leaderboard")
    lines.append("")
    lines.append("| # | Model | Params | Quality | Pass | Depth | Prefill tok/s "
                 "| Decode tok/s | TTFT | Memory | Peak | Value |")
    lines.append("|---|-------|-------:|--------:|-----:|------:|--------------:"
                 "|-------------:|-----:|-------:|-----:|------:|")
    for row in leaderboard_rows(result):
        r = row.report
        if r.error:
            lines.append(
                f"| {row.rank} | {r.model.name} | {r.model.parameter_size or '–'} "
                f"| error | – | – | – | – | – | – | – | – |"
            )
            continue
        passed = f"{r.tasks_passed}/{len(r.task_results)}" if r.task_results else "–"
        val = scores.get(r.model.name)
        val_str = f"{val:g}" if val is not None else "–"
        lines.append(
            f"| {row.rank} | {r.model.name} | {r.model.parameter_size or '–'} "
            f"| {fmt_quality(r.quality_score)} | {passed} "
            f"| {_depth_cell(row)} | {_prefill_cell(row)} | {_decode_cell(row)} "
            f"| {fmt_ttft(row.ttft_s)} | {_memory_display(r)} | {_peak_display(r)} "
            f"| {val_str} |"
        )
    lines.append("")
    lines.append("_Memory = resident model size; Peak = peak process-RSS growth "
                 "during the run (best-effort)._")
    lines.append("")

    # Per-category quality breakdown
    cats = _category_set(result)
    if cats:
        lines.append("## Quality by category")
        lines.append("")
        header = "| Model | " + " | ".join(cats) + " |"
        sep = "|-------|" + "|".join(["------:"] * len(cats)) + "|"
        lines.append(header)
        lines.append(sep)
        for r in rank_reports(result.reports):
            if r.error:
                continue
            cells = []
            for c in cats:
                scores = [t.score for t in r.task_results if t.category == c]
                cells.append(f"{100 * sum(scores) / len(scores):.0f}%" if scores else "–")
            lines.append(f"| {r.model.name} | " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by [homebench](https://github.com/Sorigra/homebench)._")
    return "\n".join(lines)


def _category_set(result: BenchmarkResult) -> List[str]:
    cats: List[str] = []
    for r in result.reports:
        for t in r.task_results:
            if t.category not in cats:
                cats.append(t.category)
    return cats


def to_json(result: BenchmarkResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent)


# ---- HTML (self-contained, shareable) --------------------------------------
_HTML_CSS = """
:root { --bg:#fff; --fg:#1c2024; --muted:#6b7280; --line:#e5e7eb; --card:#f9fafb;
        --q:#16a34a; --s:#2563eb; --bar-bg:#eef1f4; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa4b2; --line:#232833; --card:#161a21;
          --q:#22c55e; --s:#3b82f6; --bar-bg:#1c222c; } }
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:960px; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
h2 { font-size:1.05rem; margin:2rem 0 .75rem; }
.sub { color:var(--muted); font-size:.9rem; margin:0 0 1rem; }
.env { background:var(--card); border:1px solid var(--line); border-radius:8px;
       padding:.6rem .9rem; color:var(--muted); font-size:.85rem; margin:0 0 1rem; }
.verdict { background:color-mix(in srgb, var(--q) 12%, var(--bg));
           border:1px solid color-mix(in srgb, var(--q) 40%, var(--line));
           border-radius:8px; padding:.7rem 1rem; margin:0 0 1.5rem; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th,td { text-align:left; padding:.55rem .6rem; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; font-size:.78rem; text-transform:uppercase;
     letter-spacing:.03em; }
td.num,th.num { text-align:right; }
.rank { color:var(--muted); }
.model { font-weight:600; }
.bar { position:relative; min-width:120px; }
.bar .track { height:1.05rem; background:var(--bar-bg); border-radius:4px; overflow:hidden; }
.bar .fill { height:100%; border-radius:4px; }
.bar .fill.q { background:var(--q); } .bar .fill.s { background:var(--s); }
.bar .val { position:absolute; right:.4rem; top:0; font-size:.8rem; line-height:1.05rem; }
.err { color:#dc2626; font-weight:600; }
footer { margin-top:2.5rem; color:var(--muted); font-size:.82rem;
         border-top:1px solid var(--line); padding-top:1rem; }
a { color:var(--s); }
"""


def _bar(value: Optional[float], vmax: float, cls: str, label: str) -> str:
    pct = 0.0 if not value or vmax <= 0 else max(0.0, min(100.0, 100.0 * value / vmax))
    return (f'<div class="bar"><div class="track">'
            f'<div class="fill {cls}" style="width:{pct:.0f}%"></div></div>'
            f'<span class="val">{_html.escape(label)}</span></div>')


def to_html(result: BenchmarkResult, title: str = "homebench report") -> str:
    from .score import value_scores, value_verdict

    ranked = rank_reports(result.reports)
    board_rows = leaderboard_rows(result)
    ok = [r for r in ranked if not r.error]
    max_q = max((r.quality_score or 0 for r in ok), default=100) or 100
    max_tps = max((row.decode_tps for row in board_rows if not row.report.error),
                  default=1) or 1
    when = datetime.fromtimestamp(result.started_at).strftime("%Y-%m-%d %H:%M:%S")
    env = env_summary(result.environment)
    scores = value_scores(result.reports)
    verdict = value_verdict(result.reports)

    rows = []
    for row in board_rows:
        r = row.report
        name = _html.escape(r.model.name)
        params = _html.escape(r.model.parameter_size or "–")
        if r.error:
            rows.append(
                f'<tr><td class="rank">{row.rank}</td><td class="model">{name}</td>'
                f'<td class="num">{params}</td>'
                f'<td colspan="9" class="err">error: {_html.escape(r.error)}</td></tr>')
            continue
        passed = f"{r.tasks_passed}/{len(r.task_results)}" if r.task_results else "–"
        q = r.quality_score
        val = scores.get(r.model.name)
        val_str = f"{val:g}" if val is not None else "–"
        rows.append(
            f'<tr><td class="rank">{row.rank}</td><td class="model">{name}</td>'
            f'<td class="num">{params}</td>'
            f'<td>{_bar(q, max_q, "q", fmt_quality(q))}</td>'
            f'<td class="num">{passed}</td>'
            f'<td class="num">{_html.escape(_depth_cell(row))}</td>'
            f'<td class="num">{_html.escape(_prefill_cell(row))}</td>'
            f'<td>{_bar(row.decode_tps, max_tps, "s", _decode_cell(row))}</td>'
            f'<td class="num">{fmt_ttft(row.ttft_s)}</td>'
            f'<td class="num">{_memory_display(r)}</td>'
            f'<td class="num">{_peak_display(r)}</td>'
            f'<td class="num"><strong>{val_str}</strong></td></tr>')

    # per-category quality
    cats = _category_set(result)
    cat_html = ""
    if cats:
        head = "".join(f"<th class='num'>{_html.escape(c)}</th>" for c in cats)
        body = []
        for r in ranked:
            if r.error:
                continue
            cells = []
            for c in cats:
                scores = [t.score for t in r.task_results if t.category == c]
                cells.append(f"<td class='num'>{100*sum(scores)/len(scores):.0f}%</td>"
                             if scores else "<td class='num'>–</td>")
            body.append(f"<tr><td class='model'>{_html.escape(r.model.name)}</td>"
                        + "".join(cells) + "</tr>")
        cat_html = (f"<h2>Quality by category</h2><table><thead><tr>"
                    f"<th>Model</th>{head}</tr></thead><tbody>"
                    + "".join(body) + "</tbody></table>")

    env_html = f'<div class="env">{_html.escape(env)}</div>' if env else ""
    verdict_html = (f'<div class="verdict">🏆 <strong>Best value for your laptop:</strong> '
                    f'{_html.escape(verdict)}</div>') if verdict else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title><style>{_HTML_CSS}</style></head>
<body><div class="wrap">
<h1>{_html.escape(title)}</h1>
<p class="sub">{_html.escape(result.provider)} · {len(result.reports)} model(s) · {when}</p>
{env_html}
{verdict_html}
<h2>Leaderboard</h2>
<table><thead><tr><th class="num">#</th><th>Model</th><th class="num">Params</th>
<th>Quality</th><th class="num">Pass</th><th class="num">Depth</th>
<th class="num">Prefill tok/s</th><th>Decode tok/s</th><th class="num">TTFT</th>
<th class="num">Memory</th><th class="num">Peak</th><th class="num">Value</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="sub">Memory = resident model size · Peak = peak process-RSS growth during the run (best-effort)</p>
{cat_html}
<footer>Generated by <a href="https://github.com/Sorigra/homebench">homebench</a>
— a local-first LLM benchmark. Numbers reflect this machine at run time; see the
project's Limitations.</footer>
</div></body></html>
"""


# ---- hardware / model-fit --------------------------------------------------
def hardware_table(hw) -> Table:
    """Render captured hardware as a key/value summary."""
    budget, label = hw.memory_budget()
    t = Table(title="This machine", header_style="bold cyan", show_header=False)
    t.add_column("k", style="bold", justify="right")
    t.add_column("v")
    t.add_row("OS", f"{hw.os} {hw.os_version} ({hw.arch})")
    t.add_row("CPU", f"{hw.cpu}  ·  {hw.cpu_cores} cores")
    t.add_row("RAM", f"{fmt_bytes(hw.ram_total_bytes)} total  "
                     f"· {fmt_bytes(hw.ram_available_bytes)} available")
    if hw.gpu.kind == "nvidia":
        t.add_row("GPU", f"{hw.gpu.name}  · {fmt_bytes(hw.gpu.vram_bytes)} VRAM")
    elif hw.gpu.kind == "apple":
        t.add_row("GPU", f"{hw.gpu.name} (unified memory)")
    else:
        t.add_row("GPU", "none detected (CPU inference)")
    t.add_row("Model budget", f"[green]{fmt_bytes(budget)}[/green]  ({label})")
    return t


_FIT_MARK = {
    "fits": "[green]✓ fits[/green]",
    "tight": "[yellow]⚠ tight[/yellow]",
    "no": "[red]✗ too big[/red]",
}


def fit_table(results, show_all: bool = False) -> Table:
    """Render model-fit results (from catalog.evaluate_catalog)."""
    t = Table(
        title="Model fit for your hardware", header_style="bold cyan",
        caption="Install: [b]ollama pull <tag>[/b]  ·  HuggingFace repos also "
                "work in LM Studio & vLLM",
        caption_justify="left",
    )
    t.add_column("Model", style="bold", no_wrap=True)
    t.add_column("Params", justify="right")
    t.add_column("Quant", justify="center")
    t.add_column("~Needs", justify="right")
    t.add_column("Fit", justify="left", no_wrap=True)
    t.add_column("Ollama tag", overflow="fold")
    t.add_column("HuggingFace repo", overflow="fold", style="dim")

    for r in results:
        if not show_all and r.status == "no":
            continue
        m = r.model
        t.add_row(
            m.name,
            f"{m.params_b:g}B",
            r.quant or "–",
            fmt_bytes(r.required_bytes),
            _FIT_MARK.get(r.status, r.status),
            m.ollama or "–",
            m.hf or "–",
        )
    return t


# ---- throughput ------------------------------------------------------------
def throughput_table(result) -> Table:
    """Render a ThroughputResult as a concurrency-sweep table."""
    title = f"Batch throughput — {result.model} ({result.provider})"
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Conc", justify="right")
    table.add_column("Reqs", justify="right")
    table.add_column("Agg tok/s", justify="right", style="green")
    table.add_column("Speedup", justify="right")
    table.add_column("Req tok/s", justify="right")
    table.add_column("Mean lat", justify="right")
    table.add_column("p95 lat", justify="right")
    table.add_column("Errors", justify="right")

    if result.error:
        table.add_row("–", "–", "[red]error[/red]", "–", "–", "–", "–", "–")
        return table

    for p in result.points:
        speedup = result.speedup(p)
        speedup_txt = f"{speedup:.2f}×" if speedup is not None else "–"
        errors_txt = f"[red]{p.errors}[/red]" if p.errors else "0"
        table.add_row(
            str(p.concurrency),
            str(p.requests),
            f"{p.aggregate_tps:.1f}",
            speedup_txt,
            f"{p.mean_req_tps:.1f}",
            fmt_ttft(p.mean_latency_s),
            fmt_ttft(p.p95_latency_s),
            errors_txt,
        )
    return table
