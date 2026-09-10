# Repository Guidelines

## Project Structure & Module Organization

Homebench is a Python 3.9+ `src/`-layout package. `src/homebench/cli.py` defines commands, `runner.py` coordinates benchmarks, and `providers/` contains backend integrations. Lifecycle control is in `lifecycle/`, metrics in `metrics/`, and quality tasks/graders in `quality/`. Tests live in `tests/`, with shared fixtures in `conftest.py` and `fakes.py`. Keep sample task packs in `examples/` and documentation/assets in `docs/`.

This fork targets raw local-LLM performance on Ubuntu/AMD Strix Halo. The active llama.cpp ROCm router is at `127.0.0.1:8080`; models are under `/home/eskudo/ai-models`. Vulkan and vLLM underperformed in earlier local tests; treat this as environment-specific evidence and preserve raw results.

## Build, Test, and Development Commands

- `python -m venv .venv && source .venv/bin/activate`: create an environment.
- `python -m pip install -e ".[dev]"`: install editable development dependencies.
- `pytest -q`: run the CI-equivalent suite; pass a test path for a focused run.
- `homebench --help`: smoke-test the installed CLI.
- `python -m build && twine check dist/*`: validate distributions (requires `.[publish]`).

## Coding Style & Naming Conventions

Use four-space indentation, type hints on public interfaces, concise docstrings, and grouped imports. Name functions/modules `snake_case`, classes `PascalCase`, and constants `UPPER_SNAKE_CASE`. Keep provider-specific behavior in its provider module. No formatter or linter is configured; preserve nearby conventions.

Keep business logic headless so a future web API can reuse it; `tui/` only renders state. The router owns load/unload through HTTP. Do not add Docker, systemd, `sudo`, or subprocess orchestration. Never log or commit API keys.

## Testing Guidelines

Tests use pytest and `pytest-httpx`. Name files `test_<feature>.py` and functions `test_<behavior>()`. Add regression coverage, mock network providers, and retain Python 3.9–3.12 compatibility.

Live tests are opt-in: `HOMEBENCH_LIVE=1 pytest -q tests/test_live_router.py`. They touch shared services: restore model state and never run them in CI. Comparisons must hold model/GGUF, quantization, depths, concurrency, build, and effective arguments constant.

## Commit & Pull Request Guidelines

Prefer focused Conventional Commit subjects, for example `fix(vllm): count reasoning tokens`. PRs should explain user-visible effects, list validation, link issues, and include output/screenshots for UI or report changes. Update docs when commands, providers, or workflows change.
