# Guided Ops Validation

**Date**: 2026-09-10
**Spec**: `.specs/features/guided-ops/spec.md`
**Diff range**: `aafa7e3^..4ca26fc` (hotfix `4ca26fc` on `feat/guided-ops`; prior full-feature report covered `aafa7e3^..7084697`)
**Verifier**: independent sub-agent (author ≠ verifier)
**Scope**: hotfix after production crash (dotted model ids / Textual `BadIdentifier`)

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1–T16 | ✅ Done | Unchanged from prior report; all boxes remain checked in `tasks.md` |
| Hotfix GOPS-22 / GOPS-23 | ✅ Done | Execute-inline in `4ca26fc` (`panel.py`, `test_tui_panel.py`, spec ACs 8–9) |

---

## Spec-Anchored Acceptance Criteria

### P1: Instalar com perguntas (unchanged by hotfix; gate still green)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN `setup.sh` sem `--defaults` num TTY THEN perguntar host, chave, modelos com defaults no Enter | three defaults on blank stdin | `tests/test_setup.py:157` - `assert result.returncode == 0`; `tests/test_setup.py:159-161` - host/api_key_file/model_dir defaults | ✅ PASS |
| WHEN `--defaults` THEN usar `http://127.0.0.1:8080`, `~/llm-server/llama/api-key.txt`, `/home/eskudo/ai-models` | three exact default values in config | `tests/test_setup.py:81` - `assert data["host"] == "http://127.0.0.1:8080"` | ✅ PASS |
| IF `python3` < 3.9 THEN sair ≠ 0 antes de `.venv` | exit non-zero, no `.venv` | `tests/test_setup.py:125` - `assert result.returncode != 0`; `tests/test_setup.py:126` - `assert not (repo / ".venv").exists()` | ✅ PASS |
| WHEN `pip install` concluir THEN gravar `config.json` sem valor da chave | host, api_key_file, model_dir; no `api_key` field | `tests/test_setup.py:84` - `assert "api_key" not in data` | ✅ PASS |
| WHEN `~/.local/bin` gravável THEN lançador `homebench` | wrapper points to repo `.venv/bin/homebench` | `tests/test_setup.py:138` - `assert str(REPO_ROOT / ".venv" / "bin" / "homebench") in text` | ✅ PASS |
| IF `~/.local/bin` ausente/não gravável THEN imprimir `.venv/bin/homebench` e sair 0 | prints venv path, exit 0 | `tests/test_setup.py:171` - `assert result.returncode == 0`; `tests/test_setup.py:173` - `assert venv_bin in (result.stdout + result.stderr)` | ✅ PASS |
| IF checagem router falhar THEN manter venv+config, reportar, sem docker/sudo/systemd | exit 0, config exists, failure message | `tests/test_setup.py:112` - `assert result.returncode == 0`; `tests/test_setup.py:114` - `assert "router check failed" in result.stderr` | ✅ PASS |
| SHALL recusar `docker`, `sudo`, `systemctl` | script source contains none | `tests/test_setup.py:67` - `assert word not in content` | ✅ PASS |
| WHEN rerun THEN reutilizar `.venv` e sobrescrever `config.json` | second run exit 0, config present | `tests/test_setup.py:103` - `assert second.returncode == 0` | ✅ PASS |

### P1: Abrir o painel no executável (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN argv vazio + stdin/stdout TTY THEN abrir painel, não benchmark | `["panel"]` | `tests/test_cli.py:6` - `assert _inject_default_command([], stdin_is_tty=True, stdout_is_tty=True) == ["panel"]` | ✅ PASS |
| WHEN argv vazio sem TTY THEN comportar como `run` | `["run"]` | `tests/test_cli.py:5` - `assert _inject_default_command([], stdin_is_tty=False, stdout_is_tty=False) == ["run"]` | ✅ PASS |
| WHEN qualquer argumento THEN roteamento CLI atual | doctor/list/run unchanged | `tests/test_cli.py:11` - `assert _inject_default_command(["doctor"]) == ["doctor"]` | ✅ PASS |
| WHEN subcomando `panel` THEN abrir painel | parser accepts `panel` | `tests/test_cli_panel.py:16` - `assert args.command == "panel"` | ✅ PASS |
| IF `panel` sem TTY THEN sair ≠ 0 com mensagem de terminal | non-zero exit, message mentions terminal | `tests/test_cli_panel.py:22` - `assert code != 0`; `tests/test_cli_panel.py:24` - `assert "terminal" in ...` | ✅ PASS |

### P1: Faixa de status do router (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHILE Planejar/Doctor/Histórico THEN faixa com host, up/down, build, residentes | host + up/down + build + ids on sub-screens | `tests/test_tui_panel.py:40` - `assert "up" in text` (unit formatter only) | ⚠️ Spec-precision gap (strip not asserted on Plan/Doctor/History screens; carry-forward, not introduced by `4ca26fc`) |
| IF router inalcançável THEN faixa `down` + host, painel utilizável | down + host, no crash | `tests/test_tui_panel.py:70` - `assert "down" in text`; `tests/test_tui_panel.py:302` - doctor renders | ✅ PASS |
| SHALL NUNCA renderizar valor da chave API | secret absent from rendered text | `tests/test_tui_panel.py:71` - `assert SECRET not in text` | ✅ PASS |

### P1: Planejar modelos, profundidade e tipo

Prior ACs (GOPS-12..15) re-checked after widget-id change: click helper now uses `model_checkbox_id(index)`; assertions still target original router ids. Gate + sensor mutant 1 confirm these tests still exercise selection.

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN abre Planejar THEN listar ids marcáveis (GOPS-12 AC1) | two models in plan | `tests/test_tui_panel.py:113` - `assert plan.model_ids == ["alpha", "beta"]` | ✅ PASS |
| WHEN liga/desliga profundidades THEN subconjunto ordenado crescente (GOPS-12 AC2) | sorted unique depths | `tests/test_plan.py:26` - `assert plan.depths == [0, 8192, 32768]`; TUI `tests/test_tui_panel.py:114` - `assert plan.depths == [0]` | ✅ PASS |
| WHEN escolhe tipo THEN exatamente um de speed/quality/both (GOPS-12 AC3) | three modes valid | `tests/test_plan.py:19` - `assert speed_only.problems() == []` (and quality_only, both) | ✅ PASS |
| IF Rodar com zero modelos THEN recusar, permanecer, mensagem (GOPS-13) | message mentions modelo, result None | `tests/test_tui_panel.py:151` - `assert "modelo" in str(msg.render()).lower()`; `tests/test_tui_panel.py:152` - `assert app.result is None` | ✅ PASS |
| IF Rodar com zero profundidades THEN recusar, mensagem (GOPS-13) | message mentions profundidade | `tests/test_tui_panel.py:171` - `assert "profundidade" in str(msg.render()).lower()` | ✅ PASS |
| WHEN plano válido THEN gravar `last_plan` (GOPS-14) | last_plan dict in config | `tests/test_tui_panel.py:224` - `assert cfg.last_plan["model_ids"] == ["alpha", "beta"]` | ✅ PASS |
| WHEN abre com `last_plan` THEN restaurar ids existentes, descartar ausentes (GOPS-15) | alpha kept, gone dropped | `tests/test_tui_panel.py:199` - `assert plan.model_ids == ["alpha"]` | ✅ PASS |
| IF id contém caracteres que Textual rejeita (ex. `.`) THEN montar sem abortar E mostrar id original no rótulo (GOPS-22 / AC8) | no abort; checkbox label is original router id | `tests/test_tui_panel.py:241` - `assert labels == model_ids` with `model_ids = ["qwen3.8-27b-unsloth", "qwen3_8-27b-unsloth"]` (mount via `app.run_test()`; abort would fail the test) | ✅ PASS |
| WHEN marca modelo cujo id contém `.` THEN `RunPlan` e `last_plan` gravam o id original, não o widget id (GOPS-23 / AC9) | original router id in plan and persisted JSON | `tests/test_tui_panel.py:246` - `assert plan.model_ids == [dotted, underscore]`; `tests/test_tui_panel.py:250` - `assert app.result.model_ids == [dotted, underscore]`; `tests/test_tui_panel.py:255` - `assert cfg.last_plan["model_ids"] == [dotted, underscore]`; restore `tests/test_tui_panel.py:281` - `assert plan.model_ids == [dotted]` | ✅ PASS |

### P1: Rodar com confirmação e leaderboard (unchanged by hotfix; `_click_model` still selects models)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN residentes fora do plano THEN listar ids e pedir confirmação | confirmer invoked with foreign ids | `tests/test_tui_panel.py:423` - `confirmer=lambda foreign: foreign == ["foreign"]` | ⚠️ Spec-precision gap (UI listing not asserted; carry-forward, not introduced by `4ca26fc`) |
| IF recusar confirmação THEN voltar sem unload nem leaderboard | result None, unload not called | `tests/test_tui_panel.py:407` - `assert app.result is None`; `tests/test_tui_panel.py:410` - `assert unload_calls == []` | ✅ PASS |
| WHEN aceita ou desnecessário THEN entregar Runner + ModelInfo via cmd_run | force_unload Namespace to cmd_run | `tests/test_cli_panel.py:60` - `assert args.force_unload is True` | ✅ PASS |
| SHALL NÃO reimplementar medição no painel | Runner.run / run_tui not called | `tests/test_tui_panel.py:456` - `monkeypatch.setattr("homebench.runner.Runner.run", _forbidden)` | ✅ PASS |

### P1: Doctor e Histórico (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN Doctor THEN mostrar Check com nome, status, detail | ok and fail checks visible | `tests/test_tui_panel.py:302` - `assert "ok: router" in text`; `tests/test_tui_panel.py:303` - `assert "fail: models" in text` | ✅ PASS |
| WHILE Doctor aberto NÃO load/unload/alterar config | no router HTTP | `tests/test_tui_panel.py:348` - `raise AssertionError("router HTTP not allowed...")` | ✅ PASS |
| WHEN Histórico THEN listar runs mais novo primeiro | beta before alpha in text | `tests/test_tui_panel.py:341` - `assert text.index("beta") < text.index("alpha")` | ✅ PASS |
| IF sem runs THEN mensagem vazio, painel utilizável | "não há runs" message | `tests/test_tui_panel.py:318` - `assert "não há runs" in str(body.render()).lower()` | ✅ PASS |

### P2: Caminho feliz no docs/USO.md (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN guia THEN primeira seção = `./setup.sh` + `homebench` painel | lines 1–40 cite setup.sh and painel | `tests/test_uso_docs.py:10` - `assert "setup.sh" in first_40`; `tests/test_uso_docs.py:11` - `assert "painel" in first_40` | ✅ PASS |
| SHALL manter flags avançadas depois do caminho feliz | throughput after line 40 | `tests/test_uso_docs.py:19` - `assert throughput_idx >= 40` | ✅ PASS |

**Status**: ✅ All ACs covered (2 carry-forward spec-precision gaps, non-blocking; hotfix ACs GOPS-22/23 have precise evidence)

---

## Discrimination Sensor

**Baseline porcelain (real tree, pre-sensor)**: ` M setup.sh` (mode `100644` → `100755` only). Not reverted.

Scratch worktree: `/tmp/homebench-sensor-hotfix-z4iAMP` (detached HEAD `4ca26fc`); mutations only under scratch `src/homebench/tui/panel.py`; tests run with `PYTHONPATH=<scratch>/src` against repo `.venv`. Worktree removed with `git worktree remove --force`.

Unmutated scratch control: `tests/test_tui_panel.py` → 22 passed.

Real-tree porcelain post-cleanup: ` M setup.sh` (matches baseline). `git diff` of `src/homebench/tui/panel.py` and `tests/test_tui_panel.py` empty.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `src/homebench/tui/panel.py:199` | Restored production crash: `Checkbox(model_id, id=f"model-{model_id}")` | ✅ Killed (`test_plan_accepts_model_ids_with_dots` → `textual.dom.BadIdentifier: 'model-qwen3.8-27b-unsloth'`; also GOPS-12 click tests → `NoMatches('#model-0')`). 11 failed, 11 passed. |
| 2 | `src/homebench/tui/panel.py:227-230` | `_read_plan_from_ui` returns widget ids (`model-0`, `model-1`) instead of original router ids | ✅ Killed (`test_plan_accepts_model_ids_with_dots:246` - `assert plan.model_ids == [dotted, underscore]` got `['model-0', 'model-1']`; also last_plan restore). 7 failed, 15 passed. |
| 3 | `src/homebench/tui/panel.py:199` | Checkbox label set to widget id (`model_checkbox_id(index)`), not `model_id` | ✅ Killed (`test_plan_accepts_model_ids_with_dots:241` - `assert labels == model_ids` got `['model-0', 'model-1']`). 1 failed, 21 passed. |

**Sensor depth**: lightweight (3 behavior-level mutations, hotfix-focused)
**Result**: 3/3 killed

---

## Interactive UAT Results (if performed)

Not performed. Hotfix ACs are binary (no abort, original id in label/plan/JSON) and fully covered by automated tests.

---

## Code Quality

Reviewed `4ca26fc` only (`spec.md`, `src/homebench/tui/panel.py`, `tests/test_tui_panel.py`).

| Principle        | Status |
| ---------------- | ------ |
| Minimum code     | ✅ `model_checkbox_id(index)` + catalog-index widget ids; no extra abstraction |
| Surgical changes | ✅ Only plan-checkbox identity; `_click_model` helper matches the new id scheme |
| No scope creep   | ✅ Spec ACs 8–9 + one edge; no unrelated refactors |
| Matches patterns | ✅ Same Checkbox/query style as depths (`depth-{n}`) |
| Spec-anchored outcome check | ✅ Labels, RunPlan, last_plan, restore all assert original router ids |
| Per-layer Coverage Expectation | ✅ TUI `App.run_test` covers mount, click, persist, restore for dotted ids |
| Every test maps to spec requirement | ✅ New tests map to GOPS-22, GOPS-23, and the `qwen3.8` vs `qwen3_8` edge |
| Documented guidelines: `AGENTS.md` | ✅ pytest, `test_<feature>.py`, no live router, Python 3.9+ |

---

## Edge Cases

- [x] `config.json` ausente/inválido: `tests/test_config.py:27` - `assert cfg.host == "http://127.0.0.1:8080"`
- [x] Arquivo da chave ausente: `tests/test_config.py:74` - `assert config.read_api_key(...) is None`
- [x] Env vars ganham de config: `tests/test_config.py:122` - `assert os.environ[config.HOST_ENV] == "http://existing:8080"`
- [x] `setup.sh` de outro cwd: `tests/test_setup.py:93` - `assert result.returncode == 0`
- [x] Catálogo vazio em Planejar: `tests/test_tui_panel.py:128` - `assert len(list(app.query("#model-list Checkbox"))) == 0`; `tests/test_tui_panel.py:132` - `assert "modelo" in str(msg.render()).lower()`
- [x] Dois+ modelos conservados: `tests/test_plan.py:6` - `assert plan.model_ids == ["alpha", "beta"]`; TUI `tests/test_tui_panel.py:113`
- [x] Ids that differ only by an invalid widget char (`qwen3.8` vs `qwen3_8`): `tests/test_tui_panel.py:241` - `assert labels == model_ids`; `tests/test_tui_panel.py:246` - `assert plan.model_ids == [dotted, underscore]` with `qwen3.8-27b-unsloth` and `qwen3_8-27b-unsloth`

---

## Gate Check

- **Gate command**: `.venv/bin/python -m pytest -q` (from `tasks.md` Build gate; real tree, read-only)
- **Result**: 579 passed, 0 failed, 5 skipped
- **Test count before feature**: 515 collected (`aafa7e3^`)
- **Test count after prior full-feature validation**: 582 collected / 577 passed (`7084697`)
- **Test count after hotfix**: 584 collected / 579 passed (`4ca26fc`)
- **Delta (hotfix)**: +2 tests (`test_plan_accepts_model_ids_with_dots`, `test_last_plan_restores_model_ids_with_dots`)
- **Assertions**: not weakened; GOPS-12..15 still assert original router ids; click path retargeted to index widget ids
- **Skipped tests**: 5× `tests/test_live_router.py` — opt-in live router (`HOMEBENCH_LIVE=1`); justified per `AGENTS.md`
- **Failures**: none

---

## Fix Plans (if issues found)

None. Hotfix ACs and sensor are green. Two carry-forward spec-precision gaps remain optional follow-ups (status strip on sub-screens; foreign-resident UI listing).

---

## Requirement Traceability Update

Verifier did not edit `spec.md` (write surface is this report only). Intended statuses:

| Requirement | Previous Status | New Status   |
| ----------- | --------------- | ------------ |
| GOPS-01–21  | ✅ Verified (prior report) | ✅ Verified  |
| GOPS-22     | Implementing    | ✅ Verified  |
| GOPS-23     | Implementing    | ✅ Verified  |

---

## Validation

**Result**: PASS — hotfix ACs GOPS-22/AC8 and GOPS-23/AC9 have `file:line` evidence; GOPS-12..15 still hold after the widget-id change; 3/3 sensor mutants killed.

---

## Summary

**Overall**: Ready

**Spec-anchored check**: 36/36 ACs matched with `file:line` evidence; 2 carry-forward spec-precision gaps
**Sensor**: 3/3 mutations killed
**Gate**: 579 passed, 0 failed, 5 skipped

**What works**: Dotted model ids (`qwen3.8-27b-unsloth`) mount without `BadIdentifier`; checkbox labels show the original router id; RunPlan and `last_plan` persist that original id; ids that differ only by `.` vs `_` stay distinct; prior plan-screen select/save/restore ACs still pass.

**Issues found**: None blocking. Carry-forward spec-precision gaps (status strip on Plan/Doctor/History screens; foreign-resident UI listing) are unchanged by `4ca26fc`.

**Next steps**: Feature hotfix ready. Optional follow-up on the two pre-existing spec-precision gaps.
