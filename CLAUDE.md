# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`homebench` is a single-command terminal UI that benchmarks the local LLMs a user
already has (Ollama, LM Studio, llama.cpp, vLLM, MLX, or any OpenAI-compatible
server): tokens/sec, time-to-first-token, memory footprint, and a small
deterministically-graded quality suite, rendered as a live leaderboard. Local-first,
zero-config, no API keys.

The distribution name, CLI command, and import package are all `homebench` (the
name `localbench` was taken — see `RELEASING.md`).

## This fork's direction

This checkout is a fork (`Sorigra/homebench`) being adapted into a **raw performance**
benchmarking tool for local LLMs on an AMD Strix Halo mini PC. Quality testing is secondary here
(`--no-quality`). Read these before planning work on that effort:

- [`contexto-llm-benchmark.md`](contexto-llm-benchmark.md) — product goals, environment, decisions.
- [`docs/plano-modulo-ciclo-de-vida.md`](docs/plano-modulo-ciclo-de-vida.md) — plan for the model
  lifecycle module (the main gap), plus the environment findings behind it.

**Correction to the context doc:** it assumes the tool must spawn `llama-server` with flags. It
must not. The real deployment runs llama.cpp in **router mode** in Docker
(`~/llm-server/llama/docker-compose.yml`) — two backends, `llama-vulkan` on `127.0.0.1:8080` and
`llama-rocm` on `127.0.0.1:8081`, both `restart: always` and fronted by Traefik + Open WebUI. The
router already owns model lifecycle over HTTP (`GET /v1/models` reports per-model
`status.value` and the resolved argv; `POST /models/unload` works; `POST /models/load` exists
upstream but **not** in the deployed build `b10615`). So lifecycle work is an **HTTP client**, not
process or container orchestration — never kill or restart those containers.

## Commands

```bash
pip install -e ".[dev]"          # dev install (adds pytest, pytest-httpx, pyyaml)
pytest -q                        # run the whole test suite
pytest -q tests/test_runner_report.py::test_name   # single test
python -m build && twine check dist/*   # what CI's build job checks
```

There is no linter or formatter configured — match surrounding style. CI
(`.github/workflows/ci.yml`) runs `pytest -q` on Python 3.9–3.12 plus a
build/`twine check` job. Release is tag-driven (`v*` → `.github/workflows/release.yml`);
PyPI upload is still manual (`RELEASING.md`). Bump `version` in **both**
`pyproject.toml` and `src/homebench/__init__.py` for a release.

Tests never hit a network or a real backend: `conftest.py` redirects
`HOMEBENCH_HOME` to a tmp dir, `tests/fakes.py::FakeProvider` is an in-memory
provider, and HTTP-level provider tests use `pytest-httpx`.

## Architecture

Layered, small (~4.5k LOC in `src/homebench/`). Data flows:
**provider → runner → BenchmarkResult → renderer / report / history**.

- **`providers/`** — one class per backend, subclassing `Provider` (`base.py`) or
  `OpenAICompatibleProvider` (`openai_compat.py`, used by llama.cpp / vLLM / MLX /
  generic openai). A provider does three things: `list_models()`, streaming
  `generate()` (streaming so TTFT can be timed), and best-effort `memory()`.
  Registration + auto-detection order live in `providers/__init__.py`
  (`_PROVIDERS`, `_AUTO_DETECT` — `mlx` and `openai` are explicit-only). Each host
  has a default port and an env-var override (see README's Providers table).

- **`runner.py`** — the orchestrator. `RunConfig` holds all knobs; `Runner.run()`
  loops models doing warmup → speed probe → memory read → quality suite, sampling
  process RSS across the *whole* per-model run (`metrics/memory.py::RSSSampler`).
  Progress is pushed through a string-keyed **observer callback** (`EV_*`
  constants) that both renderers subscribe to. `resolve_suite()` decides the
  effective task list.

- **`quality/`** — `tasks.py` is the built-in suite (`_TASKS`, each `Task` has a
  `quick` flag for the fast default subset and a `reference` answer).
  `graders.py` holds deterministic grader factories (`exact_number`,
  `multiple_choice`, `contains_any`, `regex_match`, `valid_json`,
  `valid_json_array`). `packs.py` loads user task packs (JSON always, YAML needs
  the `yaml` extra). `judge.py` is the optional LLM-as-judge for open-ended
  (grader-less) tasks.

- **`metrics/`** — `memory.py` (RSS sampling via psutil) and `throughput.py`
  (the separate concurrency-sweep benchmark behind `homebench throughput`).

- **`models.py`** — all cross-layer types are plain dataclasses (`ModelInfo`,
  `SpeedMetrics`, `MemoryMetrics`, `TaskResult`, `ModelReport`,
  `BenchmarkResult`) with `to_dict`/`from_dict` for clean JSON round-tripping.
  `from_dict` ignores unknown keys (`_pick`) so old saved runs stay loadable.

- **`cache.py`** — `ResponseCache` keyed on (model version, task, gen params).
  Only temperature-0 responses are cached, and only the *raw response* (not the
  grade), so changing a grader still takes effect next run. Stored at
  `$HOMEBENCH_HOME/response-cache.json`.

- **`history.py`** — every run auto-saves to `$HOMEBENCH_HOME/runs/*.json`;
  provides `homebench history` and `homebench diff` (including
  `--fail-on-regression` for CI gating).

- **`hardware.py` / `catalog.py` / `hub.py`** — power `homebench fit` ("what can
  my machine run?"): capture host RAM/CPU/GPU, size a built-in ~50-model catalog
  or a live HuggingFace Hub list against the memory budget.

- **`report.py`** — Markdown / JSON / self-contained HTML export plus the shared
  Rich formatters (`fmt_tps`, `fmt_ttft`, `fmt_bytes`, `fmt_quality`) reused by
  the renderers and history.

- **`score.py`** — the composite 0–100 "value" score (`value_verdict`),
  normalised within a single run.

- **`cli.py`** — argparse. `run` is the implicit default subcommand
  (`_inject_default_command`); `_COMMANDS` must list every subcommand for that to
  work. Other subcommands: `list`, `tasks`, `history`, `diff`, `doctor`,
  `report`, `throughput`, `fit`.

- **`tui/app.py`** (Textual full-screen) and **`plainui.py`** (Rich live
  renderer, used when piped / `--no-tui` / non-TTY) are interchangeable observer
  subscribers over the same `Runner`.

`$HOMEBENCH_HOME` defaults to `~/.homebench` and holds the response cache, run
history, and HF catalog cache.

## Conventions when extending

- **New provider:** subclass `Provider` / `OpenAICompatibleProvider`, set a
  stable `name` (also the `--provider` value), register it in
  `_PROVIDERS` (and `_AUTO_DETECT` only if it has a canonical local port), add a
  row to the README Providers table.
- **New quality task:** append a `Task` to `_TASKS` in `quality/tasks.py` with a
  `reference` that actually satisfies its own grader — `test_suite.py`
  parametrizes over every task and fails otherwise. Give it `quick=True` only if
  it should run in the fast default subset.
- Keep result types as JSON-serialisable dataclasses in `models.py`; don't break
  `from_dict` compatibility with already-saved runs.
