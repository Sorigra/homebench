# Guided Ops Validation

**Date**: 2026-09-10
**Spec**: `.specs/features/guided-ops/spec.md`
**Diff range**: `aafa7e3^..2b5ddfe` (hotfix `2b5ddfe` on `feat/guided-ops`; prior dotted-id report covered `aafa7e3^..4ca26fc`)
**Verifier**: independent sub-agent (author ≠ verifier)
**Scope**: BIOS menu keyboard hotfix (arrows, Enter, Esc)

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1–T16 | ✅ Done | Unchanged; all boxes remain checked in `tasks.md` |
| Hotfix GOPS-22 / GOPS-23 | ✅ Done | Prior dotted-id hotfix `4ca26fc` |
| Hotfix GOPS-24 / GOPS-25 / GOPS-26 / GOPS-27 | ✅ Done | Execute-inline in `2b5ddfe` (`panel.py`, `test_tui_panel.py`, spec ACs 6–9) |

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

### P1: Abrir o painel no executável

Prior ACs 1–5 unchanged by hotfix; re-confirmed via gate. New ACs 6–9 are this hotfix.

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN argv vazio + stdin/stdout TTY THEN abrir painel, não benchmark (GOPS-06 AC1) | `["panel"]` | `tests/test_cli.py:6` - `assert _inject_default_command([], stdin_is_tty=True, stdout_is_tty=True) == ["panel"]` | ✅ PASS |
| WHEN argv vazio sem TTY THEN comportar como `run` (GOPS-07 AC2) | `["run"]` | `tests/test_cli.py:5` - `assert _inject_default_command([], stdin_is_tty=False, stdout_is_tty=False) == ["run"]` | ✅ PASS |
| WHEN qualquer argumento THEN roteamento CLI atual (GOPS-08 AC3) | doctor/list/run unchanged | `tests/test_cli.py:11` - `assert _inject_default_command(["doctor"]) == ["doctor"]` | ✅ PASS |
| WHEN subcomando `panel` THEN abrir painel (GOPS-08 AC4) | parser accepts `panel` | `tests/test_cli_panel.py:16` - `assert args.command == "panel"` | ✅ PASS |
| IF `panel` sem TTY THEN sair ≠ 0 com mensagem de terminal (GOPS-08 AC5) | non-zero exit, message mentions terminal | `tests/test_cli_panel.py:22` - `assert code != 0`; `tests/test_cli_panel.py:24` - `assert "terminal" in ...` | ✅ PASS |
| WHEN o painel mostra o menu principal THEN setas sobem/descem o destaque entre Planejar, Doctor, Histórico e Sair (GOPS-24 AC6) | Independent Test: down then Enter opens Doctor; three downs then Enter reaches Sair. Option order is Planejar, Doctor, Histórico, Sair | `tests/test_tui_panel.py:521` - `await pilot.press("down")`; `tests/test_tui_panel.py:525` - `assert not _view_hidden(app, "doctor")`; `tests/test_tui_panel.py:566` - `await pilot.press("down", "down", "down", "enter")`; `tests/test_tui_panel.py:567` - `assert app.result is None` | ✅ PASS |
| WHEN o operador pressiona Enter no item destacado THEN abrir essa tela, ou sair se o item for Sair (GOPS-25 AC7) | Enter on default opens Planejar; Enter on Sair quits with empty result | `tests/test_tui_panel.py:505` - `assert _view_hidden(app, "menu")`; `tests/test_tui_panel.py:506` - `assert not _view_hidden(app, "plan")`; `tests/test_tui_panel.py:524-525` - menu hidden, doctor visible; `tests/test_tui_panel.py:567` - `assert app.result is None` | ✅ PASS |
| WHEN Esc em Planejar, Doctor ou Histórico THEN voltar ao menu sem iniciar um run (GOPS-26 AC8) | Independent Test: Esc on Planejar returns to menu; `app.result is None` | `tests/test_tui_panel.py:541` - `assert not _view_hidden(app, "menu")`; `tests/test_tui_panel.py:542` - `assert _view_hidden(app, "plan")`; `tests/test_tui_panel.py:543` - `assert app.result is None` | ✅ PASS |
| WHEN Esc no menu principal THEN sair do painel com resultado vazio (GOPS-27 AC9) | quit with empty result | `tests/test_tui_panel.py:554` - `await pilot.press("escape")`; `tests/test_tui_panel.py:555` - `assert app.result is None` | ✅ PASS |

Letter shortcuts still work (existing tests, not replaced by arrows): `tests/test_tui_panel.py:90` - `await pilot.press("p")`; `:298` / `:368` - `"d"`; `:315` / `:336` / `:371` - `"h"`; `:72` / `:83` / `:474` - `"q"`; `:370` - `"m"`.

Notes on GOPS-24 / GOPS-26 (not blocking): up-arrow is not independently pressed; Histórico is not opened via arrows (letter `h` still is). Esc from Doctor/Histórico is not independently pressed; both share `action_back` else-branch with Planejar (`src/homebench/tui/panel.py:312-316`). Spec Independent Test names down+Enter→Doctor and Esc on Planejar.

### P1: Faixa de status do router (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHILE Planejar/Doctor/Histórico THEN faixa com host, up/down, build, residentes | host + up/down + build + ids on sub-screens | `tests/test_tui_panel.py:40` - `assert "up" in text` (unit formatter only) | ⚠️ Spec-precision gap (strip not asserted on Plan/Doctor/History screens; carry-forward, not introduced by `2b5ddfe`) |
| IF router inalcançável THEN faixa `down` + host, painel utilizável | down + host, no crash | `tests/test_tui_panel.py:70` - `assert "down" in text`; `tests/test_tui_panel.py:302` - doctor renders | ✅ PASS |
| SHALL NUNCA renderizar valor da chave API | secret absent from rendered text | `tests/test_tui_panel.py:71` - `assert SECRET not in text` | ✅ PASS |

### P1: Planejar modelos, profundidade e tipo (unchanged by hotfix; `_open_plan` still uses `p`)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN abre Planejar THEN listar ids marcáveis (GOPS-12 AC1) | two models in plan | `tests/test_tui_panel.py:113` - `assert plan.model_ids == ["alpha", "beta"]` | ✅ PASS |
| WHEN liga/desliga profundidades THEN subconjunto ordenado crescente (GOPS-12 AC2) | sorted unique depths | `tests/test_plan.py:26` - `assert plan.depths == [0, 8192, 32768]`; TUI `tests/test_tui_panel.py:114` - `assert plan.depths == [0]` | ✅ PASS |
| WHEN escolhe tipo THEN exatamente um de speed/quality/both (GOPS-12 AC3) | three modes valid | `tests/test_plan.py:19` - `assert speed_only.problems() == []` | ✅ PASS |
| IF Rodar com zero modelos THEN recusar, permanecer, mensagem (GOPS-13) | message mentions modelo, result None | `tests/test_tui_panel.py:151` - `assert "modelo" in str(msg.render()).lower()`; `tests/test_tui_panel.py:152` - `assert app.result is None` | ✅ PASS |
| IF Rodar com zero profundidades THEN recusar, mensagem (GOPS-13) | message mentions profundidade | `tests/test_tui_panel.py:171` - `assert "profundidade" in str(msg.render()).lower()` | ✅ PASS |
| WHEN plano válido THEN gravar `last_plan` (GOPS-14) | last_plan dict in config | `tests/test_tui_panel.py:224` - `assert cfg.last_plan["model_ids"] == ["alpha", "beta"]` | ✅ PASS |
| WHEN abre com `last_plan` THEN restaurar ids existentes, descartar ausentes (GOPS-15) | alpha kept, gone dropped | `tests/test_tui_panel.py:199` - `assert plan.model_ids == ["alpha"]` | ✅ PASS |
| IF id contém caracteres que Textual rejeita (ex. `.`) THEN montar sem abortar E mostrar id original no rótulo (GOPS-22 / AC8) | no abort; checkbox label is original router id | `tests/test_tui_panel.py:241` - `assert labels == model_ids` | ✅ PASS |
| WHEN marca modelo cujo id contém `.` THEN `RunPlan` e `last_plan` gravam o id original (GOPS-23 / AC9) | original router id in plan and persisted JSON | `tests/test_tui_panel.py:246` - `assert plan.model_ids == [dotted, underscore]`; `tests/test_tui_panel.py:255` - `assert cfg.last_plan["model_ids"] == [dotted, underscore]` | ✅ PASS |

### P1: Rodar com confirmação e leaderboard (unchanged by hotfix)

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN residentes fora do plano THEN listar ids e pedir confirmação | confirmer invoked with foreign ids | `tests/test_tui_panel.py:423` - `confirmer=lambda foreign: foreign == ["foreign"]` | ⚠️ Spec-precision gap (UI listing not asserted; carry-forward, not introduced by `2b5ddfe`) |
| IF recusar confirmação THEN voltar sem unload nem leaderboard | result None, unload not called | `tests/test_tui_panel.py:407` - `assert app.result is None`; `tests/test_tui_panel.py:410` - `assert unload_calls == []` | ✅ PASS |
| WHEN aceita ou desnecessário THEN entregar Runner + ModelInfo via cmd_run | force_unload Namespace to cmd_run | `tests/test_cli_panel.py:60` - `assert args.force_unload is True` | ✅ PASS |
| SHALL NÃO reimplementar medição no painel | Runner.run / run_tui not called | `tests/test_tui_panel.py:456` - `monkeypatch.setattr("homebench.runner.Runner.run", _forbidden)` | ✅ PASS |

### P1: Doctor e Histórico (unchanged by hotfix; still opened with `d`/`h`)

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

**Status**: ✅ All ACs covered (2 carry-forward spec-precision gaps, non-blocking; hotfix ACs GOPS-24..27 have precise evidence matching the Independent Test)

---

## Discrimination Sensor

**Baseline porcelain (real tree, pre-sensor)**: ` M setup.sh` (mode change only). Not reverted.

Scratch worktree: `/tmp/homebench-sensor-hotfix-Y11uEq` (detached HEAD `2b5ddfe`); mutations only under scratch `src/homebench/tui/panel.py`; tests run with `PYTHONPATH=<scratch>/src` against repo `.venv`. Worktree removed with `git worktree remove --force`.

Unmutated scratch control: `tests/test_tui_panel.py` → 27 passed.

Real-tree porcelain post-cleanup: ` M setup.sh` (matches baseline). `git diff` of `src/homebench/tui/panel.py` and `tests/test_tui_panel.py` empty (0 bytes).

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `src/homebench/tui/panel.py:312-316` | `action_back` always quits (`self.action_quit_panel()` even when not on menu) | ✅ Killed (`test_escape_from_plan_returns_to_menu:541` - `assert not _view_hidden(app, "menu")` got menu still hidden). 1 failed, 26 passed. |
| 2 | `src/homebench/tui/panel.py:318-328` | `on_option_list_option_selected` is a no-op (`return`) | ✅ Killed (`test_menu_enter_opens_plan:505` - `assert _view_hidden(app, "menu")` got False; also `test_menu_down_enter_opens_doctor:524`). 2 failed, 25 passed. |
| 3 | `src/homebench/tui/panel.py:159-165` | Swapped Doctor/Histórico option order so down+Enter opens Histórico | ✅ Killed (`test_menu_down_enter_opens_doctor:525` - `assert not _view_hidden(app, "doctor")` got doctor still hidden). 1 failed, 26 passed. |

**Sensor depth**: lightweight (3 behavior-level mutations, hotfix-focused)
**Result**: 3/3 killed

---

## Interactive UAT Results (if performed)

Not performed. Hotfix ACs are binary key outcomes (open screen / return to menu / quit with empty result) and fully covered by `App.run_test`.

---

## Code Quality

Reviewed `2b5ddfe` only (`spec.md`, `src/homebench/tui/panel.py`, `tests/test_tui_panel.py`).

| Principle        | Status |
| ---------------- | ------ |
| Minimum code     | ✅ OptionList + `action_back` + option-selected handler; letter bindings kept |
| Surgical changes | ✅ Menu body replaced with focusable list; `_view` tracks Esc target; tests appended |
| No scope creep   | ✅ Spec ACs 6–9 + Independent Test; no unrelated refactors |
| Matches patterns | ✅ Textual `OptionList`/`Option`, existing `BINDINGS`, `App.run_test` pilots |
| Spec-anchored outcome check | ✅ Enter opens Planejar/Doctor or quits Sair; Esc returns or quits with `result is None` |
| Per-layer Coverage Expectation | ✅ TUI `App.run_test` covers down, Enter, Esc on menu and Plan |
| Every test maps to spec requirement | ✅ New tests map to GOPS-24, GOPS-25, GOPS-26, GOPS-27; letter-key tests remain mapped to prior ACs |
| Documented guidelines: `AGENTS.md` | ✅ pytest, `test_<feature>.py`, no live router, Python 3.9+ |

---

## Edge Cases

- [x] `config.json` ausente/inválido: `tests/test_config.py:27` - `assert cfg.host == "http://127.0.0.1:8080"`
- [x] Arquivo da chave ausente: `tests/test_config.py:74` - `assert config.read_api_key(...) is None`
- [x] Env vars ganham de config: `tests/test_config.py:122` - `assert os.environ[config.HOST_ENV] == "http://existing:8080"`
- [x] `setup.sh` de outro cwd: `tests/test_setup.py:93` - `assert result.returncode == 0`
- [x] Catálogo vazio em Planejar: `tests/test_tui_panel.py:128` - `assert len(list(app.query("#model-list Checkbox"))) == 0`
- [x] Dois+ modelos conservados: `tests/test_plan.py:6` - `assert plan.model_ids == ["alpha", "beta"]`
- [x] Ids that differ only by an invalid widget char (`qwen3.8` vs `qwen3_8`): `tests/test_tui_panel.py:241` - `assert labels == model_ids`

---

## Gate Check

- **Gate command**: `.venv/bin/python -m pytest -q` (from `tasks.md` Build gate; real tree, read-only)
- **Result**: 584 passed, 0 failed, 5 skipped
- **Test count before feature**: 515 collected (`aafa7e3^`)
- **Test count after prior dotted-id hotfix**: 584 collected / 579 passed (`4ca26fc`)
- **Test count after this hotfix**: 589 collected / 584 passed (`2b5ddfe`)
- **Delta (hotfix)**: +5 tests (`test_menu_enter_opens_plan`, `test_menu_down_enter_opens_doctor`, `test_escape_from_plan_returns_to_menu`, `test_escape_on_menu_quits_panel`, `test_menu_enter_on_quit_exits`)
- **Assertions**: not weakened; letter-key tests (`p`/`d`/`h`/`q`/`m`) still present
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
| GOPS-01–23  | ✅ Verified (prior reports) | ✅ Verified  |
| GOPS-24     | Implementing    | ✅ Verified  |
| GOPS-25     | Implementing    | ✅ Verified  |
| GOPS-26     | Implementing    | ✅ Verified  |
| GOPS-27     | Implementing    | ✅ Verified  |

---

## Validation

**Result**: PASS — hotfix ACs GOPS-24/AC6, GOPS-25/AC7, GOPS-26/AC8, and GOPS-27/AC9 have `file:line` evidence matching the spec Independent Test; letter shortcuts still pass; 3/3 sensor mutants killed.

---

## Summary

**Overall**: Ready

**Spec-anchored check**: 38/40 ACs matched spec outcome; 2 carry-forward spec-precision gaps; 4/4 new hotfix ACs matched
**Sensor**: 3/3 mutations killed
**Gate**: 584 passed, 0 failed, 5 skipped

**What works**: Main menu is a focusable list. Down then Enter opens Doctor. Enter on the first item opens Planejar. Three downs then Enter quits on Sair. Esc from Planejar returns to the menu without a run. Esc on the menu quits with empty result. Letter keys `p`/`d`/`h`/`q`/`m` still work.

**Issues found**: None blocking. Carry-forward spec-precision gaps (status strip on Plan/Doctor/History screens; foreign-resident UI listing) are unchanged by `2b5ddfe`.

**Next steps**: Feature hotfix ready. Optional follow-up on the two pre-existing spec-precision gaps.
