# Model Lifecycle Validation

**Date**: 2026-08-28
**Spec**: `.specs/features/model-lifecycle/spec.md`
**Diff range**: `84a2d0e..HEAD` (branch `feat/model-lifecycle`, 17 commits, `4c23759..8ea26da`)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero
**Verdict**: ❌ **FAIL** — iteration 2 (of max 3). The iteration-1 blocker is **fixed and proven**
(M16 and its three equivalents are now killed; MLC-01/03/09/11/14 hold for multi-model runs), but
the discrimination sensor found **2 new surviving mutants inside the fix surface** (M28a, M31) and
Fix 1 silently **narrowed MLC-08 AC1**. See § Iteration 2 at the end of this file for the current
state; everything above this line is the iteration-1 report, kept as history.

> **Reading order**: §§ below up to "Summary" = **iteration 1** (2026-08-28, verdict FAIL).
> § "Iteration 2 — re-verification" at the end supersedes it where they disagree.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T1 | ✅ Done | 5 dataclasses, tolerant parsing, status normalisation |
| T2 | ✅ Done | `props()`/`is_router()` positive detection |
| T3 | ✅ Done | `list_models()`/`loaded_models()`; 17-model fixture reconstructed (declared `[~]`) |
| T4 | ✅ Done | `load()`/`unload()`, 404-as-missing-file |
| T5 | ✅ Done | `wait_until_loaded()` with injected clock, 300 s boundary tested |
| T6 | ✅ Done | Override JSON; the task's `[~]` note ("no `conftest.py` in the repo") is **factually wrong** — `/home/eskudo/homebench/conftest.py` exists and already isolates `HOMEBENCH_HOME` |
| T7 | ✅ Done | `suggest_ngl` |
| T8 | ✅ Done | `resolve()` precedence, 5 isolated tier tests |
| T9 | ✅ Done | `plan()` side-effect-free (proved by a client that raises on mutation) |
| T10 | ✅ Done | `ensure_only()` + injected `Confirmer`; `aborted` flag |
| T11 | ✅ Done | AST boundary scan, incl. self-tests that the scanner detects violations |
| T12 | ✅ Done | Real `unload()` on router hosts, per-instance probe |
| T13 | ✅ Done | `load_params` in `RunConfig` + `to_dict()` + anti-drift guard |
| T14 | ⚠️ **Partial** | Prepares only `models[0]`; models 2..N of a default 3-model run get no `ensure_only` (implementer-declared gap, confirmed by surviving mutant M16) |
| T15 | ✅ Done | `homebench models`, `_COMMANDS` parity test |
| T16 | ✅ Done | Router checks gated by `_router_expected` |
| T17 | ⚠️ **Partial** | Written and collected, **never executed** (5 skipped). MLC-15 therefore has zero executed evidence |

---

## Spec-Anchored Acceptance Criteria

### P1: Medição limpa garantida (MLC-01 … MLC-07)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — consulta ao router reporta estado ∈ {loaded, loading, unloaded} | exactly those three values; anything else must not leak | `tests/test_lifecycle_router.py:188` `assert by_id["qwen35-4b"].status == "loaded"`; `:189` `... == "loading"`; `tests/test_lifecycle_models.py:84` `assert st.status == "unloaded"` (input `"evicting"`); code `src/homebench/lifecycle/models.py:21,66` | ✅ PASS |
| AC2 — modelo alvo inexistente ⇒ `ProviderError` citando o id, sem carregar nada | error names the id; zero mutation calls | `tests/test_lifecycle_manager.py:154` `assert "ghost" in str(exc.value)`; `:161` `assert [c[0] for c in router.calls] == ["list_models"]` | ✅ PASS |
| AC3 — outros residentes ⇒ descarregar **todos** antes de medir | every other `loaded` model unloaded before the load | `tests/test_lifecycle_manager.py:101` `assert sorted(plan.to_unload) == ["resident-a", "resident-b"]`; `:225` `assert unloaded == ["resident-a", "resident-b"]`; `:228-230` load index > last unload index | ⚠️ **PASS at unit level, GAP in the shipped flow** — see Gap 1: only `models[0]` is prepared (`src/homebench/cli.py:326`), so for the default 3-model run models 2..N are never guaranteed to be alone |
| AC4 — alvo já `loaded` com os mesmos parâmetros ⇒ no-op bem-sucedido, sem descarregar/recarregar | `needs_load False`, target not unloaded, no `load` POST | `tests/test_lifecycle_manager.py:110-111` `assert plan.needs_load is False` / `assert plan.to_unload == []`; `:124` `assert plan.to_unload == ["resident"]` (target absent); `:263` `assert "load" not in _kinds(router)` | ✅ PASS (T9 deviation accepted: AC4 scopes "sem descarregar" to the **target**; AC3 still requires unloading the others) |
| AC5 — em `loading`, aguardar até 300 s antes de timeout | 300 s exactly | `tests/test_lifecycle_router.py:387` `assert "300" in str(exc.value)` (clock 1000→1301); `:397` `assert slept == [1.0]` (1299 still inside the window); `:366` `assert "300" in msg and ("timed out" in msg ...)` | ✅ PASS (both sides of the boundary asserted) |
| AC6 — carga falha/expira ⇒ `ProviderError` e nenhum modelo parcialmente carregado pelo módulo | error propagated; target unloaded on timeout | `tests/test_lifecycle_manager.py:275` `assert "bad flag -zzz" in str(exc.value)`; `:287` `assert [c[1] for c in router.calls if c[0]=="unload"] == ["target"]` | ✅ PASS ⚠️ note: cleanup runs only on the `wait_until_loaded` path — a `load()` POST that fails is re-raised **before** any best-effort unload (`src/homebench/lifecycle/manager.py:120-127`); untested and arguably in-scope for "carga falhar" |
| AC7 — chave ausente/incorreta ⇒ `ProviderError` de autenticação, sem expor a chave | message says auth rejected; key value absent | `tests/test_lifecycle_router.py:55-56` `assert "authentication" in msg.lower()...` + `assert SECRET_KEY not in msg`; `:299` same for `/models/load`; `tests/test_doctor_router.py:64-67` | ✅ PASS |

### P1: Confirmação antes de descarregar (MLC-08)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — exibir quais modelos serão descarregados e pedir confirmação antes de agir | names printed *before* the question; confirm called before any unload | `tests/test_cli_lifecycle.py:97-98` `assert "resident-a" in asked_after["output"]` (captured inside `input()`); `tests/test_lifecycle_manager.py:185` `assert "unload" not in _kinds(router)` inside the confirmer | ✅ PASS |
| AC2 — `--force-unload` descarrega sem perguntar | no `input()` call, returns True | `tests/test_cli_lifecycle.py:70` `input` monkeypatched to `pytest.fail`; `:76` `assert confirm(...) is True`; `:77` still prints the victim | ✅ PASS |
| AC3 — entrada não interativa sem a flag ⇒ abortar com mensagem de como prosseguir | refuse + name the flag | `tests/test_cli_lifecycle.py:117-119` `assert cli._make_confirmer(...)(...) is False` and `assert "--force-unload" in _out(console)` | ✅ PASS |
| AC4 — recusa ⇒ abortar sem descarregar nada e sem iniciar a medição | nothing unloaded, nothing loaded, no benchmark | `tests/test_lifecycle_manager.py:199-202` `assert outcome.aborted is True` + no `unload`/`load`; `tests/test_cli_lifecycle.py:146-148`; `:205` `assert cli.cmd_run(...) == 1` with `_build_runner` monkeypatched to `pytest.fail`; `:206` `assert [c[0] for c in ...calls] == ["list_models","list_models"]` | ✅ PASS (T10 deviation accepted: `aborted=True` instead of an exception is asserted as a **payload field**, and the CLI test proves no runner is built) |

### P1: `unload()` real no provider llamacpp (MLC-14)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — runner chama `unload()` ⇒ `POST /models/unload` | one POST, body `{"model": id}` | `tests/test_llamacpp_router.py:45-46` `assert len(posts) == 1` / `assert json.loads(posts[0].content) == {"model": "qwen35-4b"}`; runner→provider link covered by pre-existing `tests/test_runner_report.py::test_unload_called_between_models` (mutation M26 killed) | ✅ PASS |
| AC2 — falha de unload é registrada sem interromper o run | recorded, no raise | `tests/test_llamacpp_router.py:59-60` `assert provider.last_unload_error` + `assert "instance busy" in provider.last_unload_error`; `:70` network failure names the host | ⚠️ **Spec-precision gap** — spec says "registrar a falha" without saying where. `last_unload_error` is written but **read by nothing** in `src/` (grep: only tests). The failure is invisible to the user (T12 deviation) |
| AC3 — `unload()` segue no-op nos providers não-router | returns None, no HTTP | `tests/test_llamacpp_router.py:90-93` (llamacpp on a non-router host); `:150-152` parametrized over `OpenAICompatibleProvider`/`VLLM`/`LMStudio`: `assert provider.unload(...) is None` and `assert httpx_mock.get_requests() == []`; `:162` ollama unchanged | ✅ PASS |

### P2: Parâmetros de carga controláveis (MLC-09, MLC-13)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — precedência flag > JSON > preset > heurística > default | each tier beats the one below, `origin` names the winner | `tests/test_lifecycle_params.py:126-127` (`explicit`), `:135-136` (`json`), `:145-146` (`preset`), `:151` (`heuristic`), `:157-158` (`default`) — 5 isolated tests asserting both `extra_args` and `origin` | ✅ PASS |
| AC2 — parâmetros extras enviados em `extra_args` no `POST /models/load` | body carries them; omitted when empty | `tests/test_lifecycle_router.py:253-256` `assert _sent_body(...) == {"model": ..., "extra_args": ["-ngl","20","-fa"]}`; `:247`, `:262` omission | ✅ PASS |
| AC3 — router recusa ⇒ propagar a mensagem do router sem reinterpretar | router's own words present verbatim | `tests/test_lifecycle_router.py:292` `assert "unknown model id: ghost-model" in text` | ✅ PASS |
| AC4 — parâmetros efetivos gravados no resultado salvo; dois runs distinguíveis | both argv values readable from the saved JSON | `tests/test_runner_load_params.py:69-70` `assert sorted(saved) == [["-ngl","20"], ["-ngl","99"]]` (read back through `list_runs()`); `:45` `assert cfg.to_dict()["load_params"] == {...}`; anti-drift `:55` | ✅ PASS for the persistence layer ⚠️ only `models[0]` ever populates it (Gap 1); `cmd_run → _build_runner(load_params=…)` wiring itself has no test |
| AC5 — sem preset nem override ⇒ derivar `-ngl` do tamanho do arquivo e do orçamento | heuristic used when nothing else applies | `tests/test_lifecycle_params.py:151-152` `assert lp.origin == "heuristic"` | ⚠️ **GAP (unreachable)** — no caller in `src/` ever passes `hardware=`/`file_bytes=`: `src/homebench/cli.py:328` calls `resolve(state, overrides=load_overrides())`. Since the router populates `status.args` even when unloaded, the shipped path always resolves to `preset`. The tier is unit-tested dead code |

### P2: Inspeção e diagnóstico (MLC-10, MLC-12)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — subcomando lista cada modelo com estado; residentes mostram parâmetros efetivos | all three states shown; resident argv shown, non-resident argv not | `tests/test_cli_models_command.py:63-66` (names + all three states); `:77-79` `assert "-ngl 99" in out` **and** `assert "-ngl 12" not in out` **and** build id present; `:89` `assert "3 model(s) · 1 resident" in ...` | ✅ PASS |
| AC2 — `doctor` contra provider router inclui alcançabilidade e autenticação | an `ok` check citing build + resident count; auth failure is `fail` | `tests/test_doctor_router.py:36-41` `assert check.status == "ok"` + build + `"2 resident"` + host; `:64-67` `fail` + key absent + `"LLAMACPP_API_KEY"` present; `:131-133` check reaches `run_checks()` | ✅ PASS (T16 gating accepted: `_router_expected` is asserted in both directions at `:106-117`, and a non-router llama.cpp host as `info` at `:97-98` is not contradicted by any spec-defined outcome) |
| AC3 — router inalcançável ⇒ `fail` com o host, sem stack trace | status `fail`, host cited, no traceback | `tests/test_doctor_router.py:74-77` `assert check.status == "fail"` + `assert HOST in check.detail` + `assert "Traceback" not in check.detail`; CLI equivalent `tests/test_cli_models_command.py:101-103` | ✅ PASS |

### P3: Comparar backends Vulkan vs ROCm (MLC-15)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AC1 — dois hosts de router indicados ⇒ medir o mesmo modelo em cada um e **apresentar os resultados lado a lado** | a run/report that shows both hosts together | no implementation found (no multi-host flag in `src/homebench/cli.py`; no side-by-side rendering). Nearest artefact `tests/test_live_router.py:127-156`, parametrized per host, **skipped** (`:24-27`) | ❌ **GAP — no evidence** |

**Status**: ❌ Gaps present (1 shipped-flow gap on a P1 story, 1 unimplemented P3 requirement,
1 unreachable P2 tier) + 2 spec-precision gaps.

---

## Edge Cases

| Edge case (spec.md § Edge Cases) | `file:line` + assertion | Result |
| --- | --- | --- |
| 404 `File Not Found` no `load` ⇒ arquivo de modelo ausente, citando o id, nunca rota | `tests/test_lifecycle_router.py:276-279` `assert "ghost-model" in ...` + `assert "model file not found" in msg` + `assert "route not found" not in msg` | ✅ Handled |
| Container do router reinicia durante a medição ⇒ falha só o modelo corrente, demais seguem | behaviour exists pre-existing at `src/homebench/runner.py:182-184` (`except ProviderError: report.error = ...`), but **no test in the diff surface** asserts a mid-run `ProviderError` isolates to one `ModelReport` | ❌ **No evidence** (MLC-11) |
| `--models-max` atingido durante uma carga ⇒ descarregar o residente mais antigo e tentar de novo | no retry path, no notion of "oldest resident" anywhere in `src/homebench/lifecycle/` | ❌ **Not implemented, not tested** |
| Requisição de inferência em voo no modelo a descarregar ⇒ avisar antes de pedir confirmação | `src/homebench/cli.py:289-306` prints only the model list; no in-flight probe exists | ❌ **Not implemented, not tested** |
| Override JSON malformado ⇒ avisar e seguir com a precedência restante | `tests/test_lifecycle_params.py:43-45` `with pytest.warns(UserWarning)` + `assert result == {}`; `:48-53` non-object JSON | ✅ Handled |
| Mesmo modelo nos dois backends com ids diferentes ⇒ entradas independentes, sem deduplicar | no test; behaviour is implicit (one client per host) | ❌ **No evidence** |

---

## Discrimination Sensor

**Depth**: P0-full (26 behaviour-level mutations — this feature gates measurement integrity and
issues destructive unloads against a production host).
**Method**: temporary `git worktree` at `HEAD` under the scratchpad, `PYTHONPATH` pointed at the
scratch `src/`, full suite per mutation, file restored in a `finally`. The real tree was never
written to. `git stash` was not used.

| # | File:line | Mutation | Killed? | Killed by |
| --- | --- | --- | --- | --- |
| M1 | `lifecycle/router.py:143` | 404 message re-interpreted as a missing **route** instead of a missing model file | ✅ | `test_load_404_is_missing_model_file_citing_id_not_route`, `test_unload_404_...` |
| M2 | `cli.py:304` | non-interactive branch returns `True` (unload without confirmation) | ✅ | `test_non_interactive_without_the_flag_refuses_and_explains` |
| M3 | `lifecycle/manager.py:114` | refusal ignored — proceed after `confirm()` returns False | ✅ | `test_ensure_only_refusal_...`, `test_refusal_unloads_nothing_and_stops_the_run`, `test_cmd_run_returns_nonzero_...` |
| M4 | `lifecycle/params.py:101-106` | precedence swapped: server preset beats the JSON override | ✅ | `test_json_override_beats_server_preset`, `test_json_override_is_sent_as_extra_args` |
| M5 | `lifecycle/router.py:25` | default load timeout 300 s → 600 s | ✅ | `test_wait_default_timeout_is_300_seconds` |
| M6 | `lifecycle/router.py:171` | `wait_until_loaded` returns as soon as the model is *listed*, ignoring `status == "loaded"` | ✅ | 4 wait tests incl. `test_wait_times_out_with_providererror` |
| M7 | `lifecycle/manager.py:16` | `import rich` added to the lifecycle package (boundary break) | ✅ | `test_lifecycle_module_imports_nothing_forbidden[manager.py]` |
| M8 | `runner.py:75` | new `RunConfig` field added without a `to_dict()` entry | ✅ | `test_to_dict_serialises_every_runconfig_field` |
| M9 | `cli.py:191` | `"models"` dropped from `_COMMANDS` | ✅ | 11 tests incl. the `_COMMANDS`-parity parametrisation |
| M10 | `lifecycle/manager.py:67` | unload all-but-one other resident (off-by-one on "todos os outros") | ✅ | `test_plan_unloads_every_other_resident_model` + 8 more |
| M11 | `providers/llamacpp.py:63` | unload failure swallowed without recording | ✅ | `test_unload_failure_is_recorded_and_does_not_raise` |
| M12 | `doctor.py:67` | unreachable/auth-rejected router downgraded from `fail` to `info` | ✅ | `test_unreachable_router_fails_citing_the_host`, `test_rejected_key_fails_...` |
| M13 | `lifecycle/manager.py:70` | already-loaded target treated as satisfied regardless of params | ✅ | `test_plan_reloads_target_when_params_differ` |
| M14 | `lifecycle/models.py:66` | unknown status no longer normalised to `unloaded` | ✅ | `test_modelstate_unknown_status_normalises_to_unloaded` +1 |
| M15 | `lifecycle/router.py:120` | `extra_args` always sent, even when empty | ✅ | `test_load_sends_model_only_when_no_extra_args` +1 |
| **M16** | `cli.py:326` | `target = models[0]` → `models[-1]` (which selected model gets `ensure_only`) | ❌ **SURVIVED** | — full suite: 349 passed |
| M17 | `cli.py:285` | `preset` added to `_SENDABLE_ORIGINS` (server argv echoed back) | ✅ | `test_server_resolved_preset_is_not_echoed_back_as_extra_args` +1 |
| M18 | `lifecycle/manager.py:121` | resolved `extra_args` dropped from the `load` call | ✅ | 3 tests |
| M19 | `lifecycle/manager.py:131` | `effective_args` returned empty | ✅ | 3 tests |
| M20 | `lifecycle/manager.py:125-126` | best-effort unload after a timed-out load removed | ✅ | `test_ensure_only_unloads_the_target_when_the_load_times_out` |
| M21 | `doctor.py:52` | `_router_expected` always True (router check for Ollama-only users) | ✅ | `test_router_check_is_skipped_without_a_llamacpp_host` |
| M22 | `lifecycle/router.py:67` | 401 no longer treated as an auth failure (403 only) | ✅ | `test_rejected_key_fails_without_showing_the_key` |
| M23 | `lifecycle/params.py:52-53` | malformed override file re-raises instead of degrading | ✅ | `test_malformed_json_returns_empty_and_warns_without_raising` |
| M24 | `cli.py:447` | `homebench models` shows argv for unloaded models too | ✅ | `test_resident_models_show_their_effective_parameters` |
| M25 | `providers/llamacpp.py:41` | router capability cached globally across instances (AD-004 break) | ✅ | 6 tests incl. `test_router_capability_is_probed_per_instance` |
| M26 | `runner.py:180-181` | `unload_between` no longer calls `provider.unload()` | ✅ | `test_unload_called_between_models` (pre-existing) |

**Result**: 25/26 killed, **1 survived (M16)** — FAIL.
The surviving mutant is the empirical proof of Gap 1: no test exercises `_prepare_router_models`
with more than one selected model, and the default run selects three (`src/homebench/cli.py:250`).

**Isolation verified**: `git worktree list` shows only `/home/eskudo/homebench`;
`git status --porcelain` is empty, identical to the pre-sensor baseline.

---

## Gate Check

- **Gate command (Build)**: `.venv/bin/python -m pytest -q && .venv/bin/python -m build`
- **Result**: **349 passed, 5 skipped, 0 failed**; `build` → `homebench-0.11.0.tar.gz` +
  `homebench-0.11.0-py3-none-any.whl`, exit 0.
- **Test count before feature**: 162 · **after**: 349 · **Delta**: +187
- **Skipped (5, all justified)**: the whole of `tests/test_live_router.py`, gated on
  `HOMEBENCH_LIVE=1` (`:24-27`) so CI never touches the production routers. **Consequence:** the
  only artefact tied to MLC-15 never executes, so that requirement has zero executed evidence.
- **Test integrity**: no test deleted, no assertion weakened; the diff only adds files plus
  additive edits to `cli.py`, `doctor.py`, `runner.py`, `providers/llamacpp.py`.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code | ✅ small, focused modules; no speculative abstraction |
| Surgical changes | ✅ existing files touched only where the tasks required |
| No scope creep | ✅ pre-existing debts (TD-01 `size_bytes`, `reasoning_content`) correctly left alone |
| Matches patterns | ✅ `_pick`, `ProviderError`, `Check`, `cmd_*(args, console) -> int`, `pytest-httpx` all reused |
| Spec-anchored outcome check | ⚠️ 2 spec-precision gaps flagged (MLC-14 AC2 "registrar"; MLC-10 mapped to two different stories inside spec.md) |
| Per-layer Coverage Expectation met | ⚠️ router client / params / manager: every branch covered. **Integration layer misses the multi-model CLI path** (matrix row "Integração … caminho feliz + todo caminho de erro") |
| Every test maps to a spec requirement — no unclaimed tests | ✅ every new test file names its MLC ids in its docstring |
| Documented guidelines followed | ✅ none exist (no ruff/black/mypy/coverage config); strong defaults applied, `CLAUDE.md` conventions respected |
| Headless boundary (AD-005) | ✅ enforced by an AST test that is itself tested (M7 killed) |
| No container/process control (Success Criterion 5) | ✅ grep: no `subprocess`, `docker`, `systemctl` anywhere in the diff |
| API key never logged/committed | ✅ `_auth_error()` never interpolates the key; asserted at `tests/test_lifecycle_router.py:56`, `tests/test_doctor_router.py:65`, `tests/test_cli_models_command.py:114` |

---

## Fix Plans

### Fix 1 (Blocker) — `ensure_only` runs for every selected model, not just the first

- **Root cause**: `src/homebench/cli.py:326` `target = models[0].name`; `_prepare_router_models`
  is called once, before `Runner.run()`. The default run measures 3 models
  (`src/homebench/cli.py:250`). For models 2..N the "only the target is resident" guarantee is
  never established: with `--no-unload` the previous model stays resident and contends for VRAM
  (exactly the defect MLC-01/MLC-03 exist to prevent); without it, the model is unloaded and
  nothing loads the next one — and the deployment reports `models_autoload: false` (AD-001), so
  models 2..N may not be resident at measurement time at all.
- **Fix task**: give the runner a per-model preparation hook (or drive `ensure_only` from the
  model loop), so the guarantee and the recorded `load_params` apply to every measured model.
- **Verify**: a test that passes ≥2 models through the flow and asserts `ensure_only` ran per
  model and `load_params` has an entry per model — mutation M16 (`models[0]` → `models[-1]`)
  must then be killed.
- **Priority**: Blocker (P1 MVP story, default code path).

### Fix 2 (Major) — MLC-15 has no implementation and no executed evidence

- **Root cause**: no CLI surface accepts two router hosts, and nothing renders results side by
  side. `spec.md` lists MLC-15 as active; `tasks.md` maps it to T17, a live test that is skipped.
- **Fix task**: either implement the two-host comparison, or move MLC-15 to `Deferred` in the
  spec's traceability table with a recorded decision.
- **Priority**: Major.

### Fix 3 (Major) — two listed Edge Cases are unimplemented

- `--models-max` reached during a load ⇒ unload the oldest resident and retry: no code, no test.
- In-flight inference request on a model about to be unloaded ⇒ warn before the confirmation
  prompt: no code, no test (the confirmer prints only names, `src/homebench/cli.py:289-306`).
- **Fix task**: implement both, or move them out of `Edge Cases` with a recorded decision.
- **Priority**: Major (the second one is user-facing and was the stated reason for AD-002).

### Fix 4 (Major) — MLC-11 has no test in the diff surface

- **Root cause**: the isolation behaviour lives in pre-existing `runner.py:182-184`; no test
  asserts that a mid-run `ProviderError` fails only the current `ModelReport`.
- **Fix task**: a `Runner.run()` test with a provider that raises `ProviderError` for model 2 —
  assert `reports[1].error` is set and models 1 and 3 still produce metrics.
- **Priority**: Major.

### Fix 5 (Minor) — the `-ngl` heuristic tier is unreachable in production

- **Root cause**: `src/homebench/cli.py:328` never passes `hardware=`/`file_bytes=`, and the
  router always fills `status.args`, so `origin` is always `preset`. P2 AC5 works only in tests.
- **Fix task**: pass `hardware.capture()` and the model file size (available from the `-m` path
  in `status.args`) into `resolve()`, or record the tier as deferred.
- **Priority**: Minor.

### Fix 6 (Minor) — `last_unload_error` is written and never read

- **Root cause**: `src/homebench/providers/llamacpp.py:63`; grep shows no reader in `src/`.
  MLC-14 AC2 "registrar a falha" is satisfied only in the weakest sense.
- **Fix task**: surface it once per run (observer event or end-of-run note), or amend the spec.
- **Priority**: Minor.

### Fix 7 (Minor) — no evidence for two edge cases and one wiring path

- Same model on both backends must not be deduplicated: add a test.
- `cmd_run → _build_runner(load_params=…)` is untested.
- A `load()` POST that fails skips the best-effort unload (`manager.py:120-127`) — decide whether
  AC6 covers it, then test it.
- **Priority**: Minor.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| MLC-01 | Pending | ⚠️ Verified at unit level; not guaranteed for models 2..N |
| MLC-02 | Pending | ✅ Verified |
| MLC-03 | Pending | ⚠️ Verified at unit level; not guaranteed for models 2..N |
| MLC-04 | Pending | ✅ Verified |
| MLC-05 | Pending | ✅ Verified |
| MLC-06 | Pending | ✅ Verified (timeout path; failed-`load` path untested) |
| MLC-07 | Pending | ✅ Verified |
| MLC-08 | Pending | ✅ Verified |
| MLC-09 | Pending | ⚠️ Verified for the persistence layer; populated only for `models[0]` |
| MLC-10 | Pending | ✅ Verified |
| MLC-11 | Pending | ❌ Needs test |
| MLC-12 | Pending | ✅ Verified |
| MLC-13 | Pending | ⚠️ Verified except the heuristic tier, which no caller can reach |
| MLC-14 | Pending | ✅ Verified (⚠️ "registrar" is inspection-only) |
| MLC-15 | Pending | ❌ Not implemented |

---

## Summary

**Overall**: ❌ Not Ready

**Spec-anchored check**: 22 of 26 acceptance criteria matched their spec-defined outcome ·
1 AC unimplemented (MLC-15) · 3 ACs pass at unit level but not in the shipped flow
(MLC-01/03/09 for multi-model runs, MLC-13's heuristic tier) · 2 spec-precision gaps flagged.
Edge cases: 2 of 6 covered, 4 without evidence.
**Sensor**: 25/26 killed, 1 survived (M16).
**Gate**: 349 passed, 0 failed, 5 skipped (justified), `build` clean.

**What works**: the router HTTP client (auth, 404-as-file, timeout boundary, message
propagation), the planner/executor pair with the injected confirmer, the headless boundary,
the `models` subcommand, the doctor checks, the persistence of load params, and both anti-drift
guards (`to_dict` allowlist and `_COMMANDS`) — all of them empirically discriminating.

**Issues found**: see Fix Plans 1–7; Fix 1 is the blocker.

**Next steps**: route Fix 1–4 to an implementer, re-verify (iteration 1 of max 3).

---
---

# Iteration 2 — re-verification (2026-08-28)

**Diff range re-verified**: `8ea26da..HEAD` (fix-only; `16ced38` in that range is the iteration-1
report + lessons, no product code). Full feature range `84a2d0e..HEAD`.
**Fix commits**: `a374c5b` (Fix 6 → MLC-14 AC2) · `260d110` (Fix 1 → MLC-01/03/09, the blocker) ·
`211d957` (Fix 4 → MLC-11, MLC-06).
**Verifier**: fresh independent sub-agent, coverage re-derived from `spec.md`, evidence-or-zero.
**Verdict**: ❌ **FAIL** — blocker fixed, 2 new surviving mutants + 1 undocumented AC narrowing.

## What changed in the product

`Runner` gained a `prepare_model` hook (`src/homebench/runner.py:118`, called at
`:182-186` before warmup, inside the per-model `try`), `_prepared_params` is merged into
`result.config["load_params"]` at `:150-153`, `ModelReport.warnings` was added
(`src/homebench/models.py:122,148,159`), the best-effort unload failure is lifted onto the report
at `src/homebench/runner.py:200-206`, `plainui` prints it at `src/homebench/plainui.py:130-132`,
and `_prepare_router_models` now returns `(proceed, prepare_hook)` with a per-model closure
(`src/homebench/cli.py:310-358`).

---

## Discrimination Sensor — iteration 2

**Depth**: P0-full (16 fresh behaviour-level mutations, all aimed at the fix surface).
**Method**: temporary `git worktree add <scratchpad>/wt HEAD`, `PYTHONPATH` pointed at the scratch
`src/`, full suite per mutation, original restored in a `finally` with a re-read assertion. The
real tree was never written to. `git stash` was not used. Scratch baseline in the worktree:
370 passed, 5 skipped — identical to the real tree.

| # | File | Mutation | Killed? | Killed by |
| --- | --- | --- | --- | --- |
| **M27** | `runner.py:182` | **M16 equivalent** — hook invoked only for the **first** model of the run | ✅ Killed (5 failures) | `test_hook_is_called_once_per_model_in_order`, `test_every_model_records_its_effective_load_params_not_just_the_first`, `test_prepare_phase_event_is_emitted_per_model`, +2 |
| **M27b** | `runner.py:145` | **M16 equivalent** — hook invoked only for the **last** model | ✅ Killed (5 failures) | same set + `test_hook_error_fails_only_that_model` |
| **M28b** | `cli.py:355` | **M16 equivalent at the CLI layer** — `ensure_only(models[0].name, …)` regardless of the argument | ✅ Killed | `test_hook_makes_each_model_the_sole_resident_and_reports_its_args` |
| M28a | `cli.py:349` | closure resolves the **state/params of `models[0]`** instead of the model it was handed | ❌ **SURVIVED** — 370 passed | — |
| M29 | `runner.py:185-186` | hook result never recorded into `_prepared_params` | ✅ Killed (4) | 4 × `test_runner_prepare_hook.py` |
| M30 | `runner.py:153` | merged `load_params` never written back to `result.config` | ✅ Killed (4) | 4 × `test_runner_prepare_hook.py` |
| M30b | `runner.py:151` | merge discards the `RunConfig.load_params` base | ✅ Killed | `test_base_config_load_params_are_merged_with_hook_results` |
| M31 | `runner.py:182-190` | `phase="prepare"` block moved **after** warmup | ❌ **SURVIVED** — 370 passed | — |
| M32 | `runner.py:184` | hook's `ProviderError` re-raised as `RuntimeError` (escapes per-model isolation) | ✅ Killed | `test_hook_error_fails_only_that_model` |
| M33 | `runner.py:204` | `report.warnings.append(...)` removed (Fix 6) | ✅ Killed (3) | `test_unload_failure_is_recorded_on_the_report_warnings`, `test_warnings_survive_json_round_trip`, `test_plainui_prints_the_warning_after_the_leaderboard` |
| M34 | `runner.py:201-202` | `last_unload_error` read **before** the unload call (Fix 6) | ✅ Killed (3) | `test_unload_failure_is_recorded_...`, `test_unload_failure_emits_a_warning_phase_event`, `test_warnings_survive_json_round_trip` |
| M35 | `runner.py:208` | mid-run `ProviderError` swallowed, `report.error` left unset (Fix 4 target) | ✅ Killed (2) | `test_the_broken_model_is_flagged_and_the_others_still_measure`, `test_hook_error_fails_only_that_model` |
| M36 | `cli.py:335-336` | `our_names` exemption dropped — confirmation demanded for run-member residents | ✅ Killed | `test_no_confirmation_when_nothing_foreign_is_resident` |
| M37 | `cli.py:335-336` | `foreign = []` — a foreign resident is never detected, confirmation never asked | ✅ Killed (2) | `test_refusal_of_a_foreign_resident_unloads_nothing_and_stops_the_run`, `test_cmd_run_returns_nonzero_and_never_benchmarks_on_refusal` |
| M38 | `cli.py:340` | refusal of a foreign resident ignored, run proceeds | ✅ Killed (2) | same two |
| M39 | `cli.py:351` | server-resolved preset echoed back as `extra_args` | ✅ Killed (3) | `test_server_resolved_preset_is_not_echoed_back_as_extra_args` +2 |
| M40 | `plainui.py:130-132` | warnings not printed after the leaderboard | ✅ Killed | `test_plainui_prints_the_warning_after_the_leaderboard` |
| M41 | `models.py:148` | `warnings` emptied on serialisation | ✅ Killed | `test_warnings_survive_json_round_trip` |

**Result**: **16/18 killed, 2 survived** — ❌ FAIL.
**M16 status: KILLED** — all three of its equivalents (M27, M27b, M28b) fail the suite. The
iteration-1 blocker is empirically closed.

**Isolation verified**: `git worktree remove --force` + `git worktree prune` run;
`git worktree list` shows only `/home/eskudo/homebench`; `git status --porcelain` is empty,
identical to the pre-sensor baseline.

### Surviving mutant analysis

**M28a — the params half of the per-model closure is still single-model-tested.**
`src/homebench/cli.py:349` resolves `state` for the model it is handed; pointing it at
`models[0]` instead changes nothing that any test observes. Consequence in production: with a
`$HOMEBENCH_HOME/load-params.json` carrying different `-ngl` per model
(`src/homebench/lifecycle/params.py:101` keys overrides by `model.id`), every model after the
first would be **loaded with model 1's flags** while the recorded `effective_args` — read back
from the router at `manager.py:136-139` — would still look correct. That is a silent measurement
error of exactly the class MLC-09/MLC-13 exist to prevent. `test_json_override_is_sent_as_extra_args`
(`tests/test_cli_lifecycle.py:202-213`) and `test_server_resolved_preset_is_not_echoed_back_as_extra_args`
(`:189-199`) both drive the hook with a **single** model, so neither discriminates. This is
lesson **L-001 recurring inside the very fix that was meant to close it**.

**M31 — nothing asserts that preparation precedes warmup.**
Moving the whole `phase="prepare"` block below the `cfg.warmup` block leaves the suite green.
`tests/test_runner_prepare_hook.py:19` builds every runner with `warmup=False`, so the two steps
are never both live in one test. Consequence in production: `provider.warmup()` would fire against
a model the router has not loaded yet — and the deployment reports `models_autoload: false`
(AD-001) — so warmup would hit an unloaded model on every cold model. tasks.md F1 explicitly
lists "chamado 1×/modelo **antes do warmup**" as a Done-when criterion, and spec MLC-01/MLC-03 say
the guarantee holds "**antes de medir**"; neither is asserted.

---

## Spec-Anchored Re-check of the Affected ACs

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| **MLC-01** — estado reportado por modelo, garantia aplicada antes de medir | the guarantee is established for **every** measured model, not just one | `tests/test_runner_prepare_hook.py:28` `assert calls == ["fast:1b", "smart:8b"]`; `:85` `assert prepared == ["fast:1b", "smart:8b"]`; `tests/test_cli_lifecycle.py:182` `assert loaded == ["m1", "m2", "m3"]` | ✅ **PASS** (was ⚠️ in iteration 1) ⚠️ ordering vs warmup unasserted (M31) |
| **MLC-03** — descarregar **todos** os outros residentes antes de medir | after each model's turn only that model is resident | `tests/test_cli_lifecycle.py:183` `assert "resident" in [c[1] for c in client.calls if c[0] == "unload"]`; `:185` `assert [s.id for s in client._states if s.status == "loaded"] == ["m3"]` (3-model run, sole resident at the end) | ✅ **PASS** (was ⚠️ in iteration 1) |
| **MLC-06** — carga que falha/expira ⇒ `ProviderError`, nada parcialmente carregado | error propagated; no half-loaded model; no spurious unload | `tests/test_lifecycle_manager.py:287` `assert [s.id for s in router._states if s.status == "loaded"] == []`; `:289` `assert [c[1] for c in router.calls if c[0] == "unload"] == ["other"]`; timeout path `:275`/`:287` (iteration 1) | ✅ **PASS** — the iteration-1 note "failed-`load` POST path untested" is now closed |
| **MLC-09** — parâmetros efetivos gravados por modelo no resultado salvo | one entry **per measured model**, JSON round-trippable, merged with any config base | `tests/test_runner_prepare_hook.py:36` `assert result.config["load_params"] == {"fast:1b": ["-ngl","10"], "smart:8b": ["-ngl","20"]}`; `:44` hook returning None records nothing; `:56-58` merge with `RunConfig.load_params`; `:103` `assert restored["config"]["load_params"]["smart:8b"] == ["-ngl","42"]` | ✅ **PASS** (was ⚠️ in iteration 1) ⚠️ the *values* are only single-model-tested (M28a) |
| **MLC-11** — reinício do router no meio da medição falha só o modelo corrente | `reports[i].error` set for the broken model; the others still produce metrics; run completes | `tests/test_runner_error_isolation.py:45` `assert "connection refused: router restarting" in by_name["b:1b"].error`; `:48-51` `assert by_name["a:1b"].error is None` + `assert by_name["a:1b"].speed.tokens_per_sec > 0` (same for `c:1b`); `:58` `assert errored == ["c:1b"]`; `:63-64` `assert [...] == ["run_start", "run_done"]`. Hook-raised errors: `tests/test_runner_prepare_hook.py:71-74` | ✅ **PASS** (was ❌ in iteration 1) |
| **MLC-14 AC2** — falha de unload registrada sem interromper o run | the failure reaches the user and the saved run; the run does not fail | `tests/test_runner_unload_warning.py:47` `assert by_name["fast:1b"].warnings == ["unload failed: router said no for fast:1b"]`; `:48` `assert by_name["fast:1b"].error is None`; `:49` clean model has `warnings == []`; `:57` `phase="warning"` event; `:75` survives the JSON round trip; `:81` old saved runs load with `warnings == []`; `:90` `assert "warning" in out and "router said no for fast:1b" in out` | ✅ **PASS** — the iteration-1 spec-precision gap ("written and read by nothing") is closed |
| **MLC-08 AC1** — *regression check* — descarregar um residente exige exibir + confirmar | confirmation before **any** resident is unloaded | confirmation is now asked **only for residents that are not part of this run** (`src/homebench/cli.py:330-343`); the per-model closure passes `lambda _plan: True` (`:355`). Asserted as intended behaviour at `tests/test_cli_lifecycle.py:140-149` (`input` monkeypatched to `pytest.fail`) | ⚠️ **NARROWED, undocumented** — see Gap 3 |

**Status**: 6 of 6 re-checked ACs now match their spec-defined outcome ·
1 previously-passing AC (MLC-08 AC1) narrowed without a recorded decision ·
2 discrimination gaps (M28a, M31) sit on MLC-01/03 (ordering) and MLC-09/MLC-13 (per-model values).

---

## Assessment of the AD-006 Deferrals

Each item judged on whether the stated reason is sound or a real requirement being swept aside.

| Deferred item | Stated reason | Assessment |
| --- | --- | --- |
| **MLC-15** — comparar Vulkan vs ROCm (P3) | os dois hosts rodam builds diferentes (`b10615` vs `b10664`), a comparação mistura backend com versão | ✅ **Legitimate.** P3, never MVP, user-chosen, and now recorded as `Deferred (AD-006)` in `spec.md:255` + the status table at `:272`. ⚠️ Minor: the stated reason is about *interpretive validity*, not feasibility — the AC ("medir nos dois e apresentar lado a lado") is still implementable, and AD-004 already requires per-host `build_info`. The honest reason is "P3, out of MVP". Not a disguised failure either way. L-002 (a skipped test is zero evidence) is now respected: `tests/test_live_router.py` no longer backs any active requirement. |
| **Aviso de "requisição em voo"** antes de descarregar | build `b10615` não expõe contagem de requisições ativas em `/props`, `/v1/models` nem `/models/sse`; a confirmação obrigatória já cobre o risco de fundo | ⚠️ **Legitimate but its own mitigation was weakened in the same iteration.** The dependency limit is real (a warning cannot be built from data the router does not publish; `/slots` is a non-router endpoint), and the edge case is now annotated in `spec.md:231-233`. **But** the fallback argument — "a confirmação obrigatória (AD-002) já cobre o risco" — no longer holds as stated: Fix 1 removed the confirmation for run-member residents and for any model that becomes resident **after** the up-front check (`src/homebench/cli.py:355` `lambda _plan: True`). The deferral note should be amended, or Gap 3 fixed. |
| **`--models-max` atingido durante a carga ⇒ liberar o mais antigo e repetir** | `plan()` já descarrega todos os outros antes de carregar, o limite nunca é atingido | ✅ **Legitimate — moot by construction.** Verified in code: `src/homebench/lifecycle/manager.py:67` collects every other resident and `:117-118` unloads them all before `:121` issues the load, so the tool's own path never presents more than one instance to a `max_instances: 2` router. Residual risk is a third party loading a model between the unload loop and the load POST — a race outside the tool's control, not the deferred requirement. |
| **Heurística de `-ngl` no caminho de produção** (MLC-13 P2 AC5) | o router sempre preenche `status.args`, então `resolve()` sempre cai em `preset` | ⚠️ **Legitimate outcome, inaccurate reason.** The tier is unreachable for a stronger reason than the one recorded: `src/homebench/cli.py:350` calls `resolve(state, overrides=overrides)` and never passes `hardware=` / `file_bytes=`, so `src/homebench/lifecycle/params.py:108` (`if hardware is not None and file_bytes > 0`) can never be true **regardless** of whether a preset exists. The deferral stands (P2 AC5, user-chosen, annotated at `spec.md:270`), but `suggest_ngl` + the heuristic branch remain in `src/` reachable only from tests — lesson L-006 unaddressed. Recommend either wiring it or deleting it rather than leaving dead code. |
| **Mesmo modelo nos dois backends sem deduplicar** | N/A por construção: um client por host, um provider por run | ✅ **Legitimate.** Verified: `src/homebench/providers/llamacpp.py:41-47` probes and builds one `LlamaRouterClient` per provider instance (per host, never cached globally — AD-004, mutation M25 killed in iteration 1), and `_prepare_router_models` closes over that single `client`. With one provider per run there is no shared list in which two ids could collide. Correctly annotated as N/A in `spec.md:227-229`. |

**Verdict on the deferrals**: none is a disguised failure. Two carry reasons that are inaccurate
or now stale (in-flight warning, `-ngl` heuristic) and should be amended in AD-006.

---

## Regression Check

- **Gate**: `.venv/bin/python -m pytest -q` → **370 passed, 5 skipped, 0 failed** ·
  `.venv/bin/python -m build` → `homebench-0.11.0.tar.gz` + `…-py3-none-any.whl`, exit 0.
- **Test count**: pre-feature 162 → iteration 1: 349 → iteration 2: **370** (+21). Added:
  `tests/test_runner_prepare_hook.py` (8), `tests/test_runner_unload_warning.py` (7),
  `tests/test_runner_error_isolation.py` (3), `tests/test_lifecycle_manager.py` (+1),
  `tests/test_cli_lifecycle.py` 16 → 18 collected.
- **No coverage lost in the rewritten `tests/test_cli_lifecycle.py`**: every iteration-1 MLC-08
  assertion survives — force-unload flag (`:64-77`), names shown before the question (`:83-98`),
  answer parametrisation (`:101-109`), non-interactive refusal naming `--force-unload` (`:112-119`),
  refusal unloads nothing (`:152-164`), `cmd_run` returns 1 and builds no runner (`:219-231`).
  The single removed test (`test_approval_unloads_the_others_and_returns_effective_args`) was
  replaced by the strictly stronger multi-model `test_hook_makes_each_model_the_sole_resident_and_reports_its_args`.
- **Iteration-1 CONFIRMED-good areas untouched**: the fix diff (`8ea26da..HEAD`) modifies only
  `src/{cli,models,plainui,runner}.py` and `tests/{test_cli_lifecycle,test_lifecycle_manager}.py`.
  `tests/test_lifecycle_router.py`, `test_lifecycle_models.py`, `test_lifecycle_params.py`,
  `test_lifecycle_boundary.py`, `test_llamacpp_router.py`, `test_doctor_router.py`,
  `test_cli_models_command.py`, `test_runner_load_params.py` are byte-identical to iteration 1 —
  the router client, planner/executor, headless boundary, `models` subcommand, doctor checks and
  both anti-drift guards (`to_dict` allowlist, `_COMMANDS` parity) keep their assertions intact.
  Re-run mutations M37/M38/M39 confirm the confirmation path and the preset-echo guard still
  discriminate after the rewrite.
- **No assertion weakened, no test deleted without a stronger replacement.**
- **Success Criterion 5** (no container/process control) re-checked: no `subprocess`, `docker`,
  `systemctl` anywhere in `src/homebench/`. The API key is still never interpolated into a message.

---

## Code Quality — iteration 2 delta

| Principle | Status |
| --- | --- |
| Minimum code | ✅ the hook is ~10 lines in `runner.py`; no new module, no new abstraction |
| Surgical changes | ✅ 4 product files, all previously in scope |
| No scope creep | ✅ deferred items genuinely left out; `ModelReport.warnings` is the smallest thing that satisfies MLC-14 AC2 |
| Matches patterns | ✅ `Optional[Callable]` injection mirrors the existing `judge=`; `warnings` follows the `to_dict`/`from_dict` + tolerant-`from_dict` convention |
| Spec-anchored outcome check | ⚠️ MLC-08 AC1 narrowed without a recorded decision (Gap 3) |
| Per-layer Coverage Expectation | ⚠️ the CLI/integration layer now covers the multi-model happy path but not multi-model **parameter resolution** (M28a) or step ordering (M31) |
| Every test maps to a spec requirement | ✅ all three new test files name their MLC ids in the module docstring |
| Documented guidelines followed | ✅ none exist; strong defaults applied |

---

## Ranked Gaps — iteration 2

### Gap 1 (Major) — M28a: the closure's parameter resolution is only single-model-tested

- **Where**: `src/homebench/cli.py:349`; tests `tests/test_cli_lifecycle.py:189-213`.
- **Why it matters**: a wrong-model params lookup would silently load models 2..N with model 1's
  `-ngl`/context flags while the recorded `effective_args` still read correct — an undetectable
  measurement error, the same class MLC-09 exists to prevent.
- **Fix**: extend `test_hook_makes_each_model_the_sole_resident_and_reports_its_args` (or add one
  test) to drive ≥2 models with **distinct** `load-params.json` overrides and assert the `load`
  call for each model carries **its own** `extra_args`. Mutation M28a must then be killed.

### Gap 2 (Major) — M31: nothing asserts preparation runs before warmup

- **Where**: `src/homebench/runner.py:182-190`; tests `tests/test_runner_prepare_hook.py:19`
  disables warmup everywhere.
- **Why it matters**: with `models_autoload: false` (AD-001), warming up before the prepare hook
  loads the model would hit an unloaded model on every cold model. It is a written Done-when
  criterion (tasks.md F1) and the "antes de medir" half of MLC-01/MLC-03.
- **Fix**: one test with `warmup=True` and a provider that records call order, asserting
  `["prepare:m", "warmup:m", ...]` per model. Mutation M31 must then be killed.

### Gap 3 (Major) — Fix 1 narrowed MLC-08 AC1 without recording the decision

- **Where**: `src/homebench/cli.py:330-343` (confirmation covers only residents **not** in the
  run) and `:355` (`lambda _plan: True` for every per-model plan thereafter).
- **Why it matters**: MLC-08 AC1 is unconditional ("WHEN o módulo precisa descarregar um modelo
  residente THEN … pedir confirmação antes de agir") and AD-002 exists to protect a third party's
  Open WebUI session. Two paths now unload a resident with no prompt: (a) a resident that happens
  to be one of the run's models — and the default run auto-selects the 3 smallest of 17, so the
  user may never have named it; (b) any model loaded by someone else **after** the up-front check,
  since the per-model confirmer is hard-wired to `True` for the rest of the run. Under iteration-1
  code both were confirmed. The narrowing is explained in a code comment
  (`src/homebench/cli.py:331-334`) but appears in no AD, and AD-006's in-flight-warning deferral
  still cites this confirmation as its mitigation.
- **Fix**: either (i) record it as a decision (AD-007) and amend MLC-08 AC1 + the AD-006
  in-flight note to match, or (ii) re-check for newly-foreign residents inside `prepare` and ask
  then. Whichever is chosen, add a test for a resident that **is** part of the run.

### Gap 4 (Minor, carried) — `-ngl` heuristic tier remains dead code in `src/`

- `src/homebench/lifecycle/params.py:62-79,108-111` are reachable only from tests
  (`src/homebench/cli.py:350` never passes `hardware=`/`file_bytes=`). Deferred by AD-006, but the
  recorded reason is inaccurate (see the deferral table). Wire it or delete it.

---

## Requirement Traceability Update — iteration 2

| Requirement | Iteration 1 | Iteration 2 |
| --- | --- | --- |
| MLC-01 | ⚠️ unit-level only | ✅ **Verified** (multi-model; ⚠️ ordering unasserted — Gap 2) |
| MLC-03 | ⚠️ unit-level only | ✅ **Verified** (multi-model) |
| MLC-06 | ✅ (failed-`load` path untested) | ✅ **Verified** (both paths) |
| MLC-08 | ✅ Verified | ⚠️ **Narrowed** — AC1 no longer unconditional (Gap 3) |
| MLC-09 | ⚠️ `models[0]` only | ✅ **Verified** (per model; ⚠️ values single-model-tested — Gap 1) |
| MLC-11 | ❌ Needs test | ✅ **Verified** |
| MLC-13 | ⚠️ heuristic unreachable | ⚠️ unchanged — deferred (AD-006), Gap 4 |
| MLC-14 | ✅ (⚠️ inspection-only) | ✅ **Verified** — surfaces on `ModelReport.warnings`, in the saved run, and after the leaderboard |
| MLC-15 | ❌ Not implemented | ⏸️ **Deferred (AD-006)** — legitimate |
| MLC-02, 04, 05, 07, 10, 12 | ✅ Verified | ✅ unchanged (test files byte-identical) |

---

## Summary — iteration 2

**Overall**: ❌ Not Ready — but the blocker is closed and the remaining work is three assertions
plus one recorded decision.

**Spec-anchored check**: 6/6 re-checked ACs now match their spec-defined outcome
(MLC-01, 03, 06, 09, 11, 14) · 1 previously-passing AC narrowed (MLC-08 AC1) · 5/5 AD-006
deferrals judged legitimate (2 with reasons that need amending).
**Sensor**: 18 mutations, **16 killed, 2 survived** (M28a, M31). **M16 is KILLED** — proven by
three independent equivalents (M27, M27b, M28b).
**Gate**: 370 passed, 0 failed, 5 skipped (justified, unchanged), `build` clean.

**What now works that did not before**: the "only the target is resident" guarantee and the
per-model `load_params` record hold for **every** measured model, not just the first; a mid-run
`ProviderError` is proven to fail only the current model; a best-effort unload failure now reaches
the user and the saved run.

**Issues found**: Gaps 1–3 above (two weak-test gaps inside the fix surface, one undocumented AC
narrowing) + carried Gap 4.

**Next steps**: route Gaps 1–3 to an implementer and re-verify (iteration 3 of max 3). Gaps 1 and
2 are single tests each; Gap 3 is a decision plus either a doc amendment or a small code change.
