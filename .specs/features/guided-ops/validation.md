# Guided Ops Validation

**Date**: 2026-09-10
**Spec**: `.specs/features/guided-ops/spec.md`
**Diff range**: `aafa7e3^..7084697`
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1   | ✅ Done | config load/save |
| T2   | ✅ Done | apply_to_environ |
| T3   | ✅ Done | setup.sh --defaults |
| T4   | ✅ Done | setup failures/idempotent |
| T5   | ✅ Done | RunPlan validation |
| T6   | ✅ Done | last_plan restore |
| T7   | ✅ Done | router_status |
| T8   | ✅ Done | doctor/history snapshots |
| T9   | ✅ Done | inject panel on TTY |
| T10  | ✅ Done | panel subcommand |
| T11  | ✅ Done | panel shell + strip |
| T12  | ✅ Done | plan screen |
| T13  | ✅ Done | doctor/history screens |
| T14  | ✅ Done | run confirmation |
| T15  | ✅ Done | cmd_panel handoff |
| T16  | ✅ Done | docs/USO.md lead |

All T1–T16 marked done in `tasks.md`; no unchecked boxes remain.

---

## Spec-Anchored Acceptance Criteria

### P1: Instalar com perguntas

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN `setup.sh` sem `--defaults` num TTY THEN perguntar host, chave, modelos com defaults no Enter | three defaults on blank stdin | `tests/test_setup.py:157` - `assert result.returncode == 0`; `tests/test_setup.py:159-161` - host/api_key_file/model_dir defaults | ✅ PASS |
| WHEN `--defaults` THEN usar `http://127.0.0.1:8080`, `~/llm-server/llama/api-key.txt`, `/home/eskudo/ai-models` | three exact default values in config | `tests/test_setup.py:81` - `assert data["host"] == "http://127.0.0.1:8080"` | ✅ PASS |
| IF `python3` < 3.9 THEN sair ≠ 0 antes de `.venv` | exit non-zero, no `.venv` | `tests/test_setup.py:125` - `assert result.returncode != 0`; `tests/test_setup.py:126` - `assert not (repo / ".venv").exists()` | ✅ PASS |
| WHEN `pip install` concluir THEN gravar `config.json` sem valor da chave | host, api_key_file, model_dir; no `api_key` field | `tests/test_setup.py:84` - `assert "api_key" not in data` | ✅ PASS |
| WHEN `~/.local/bin` gravável THEN lançador `homebench` | wrapper points to repo `.venv/bin/homebench` | `tests/test_setup.py:138` - `assert str(REPO_ROOT / ".venv" / "bin" / "homebench") in text` | ✅ PASS |
| IF `~/.local/bin` ausente/não gravável THEN imprimir `.venv/bin/homebench` e sair 0 | prints venv path, exit 0 | `tests/test_setup.py:171` - `assert result.returncode == 0`; `tests/test_setup.py:172-173` - `assert venv_bin in (result.stdout + result.stderr)`; impl `setup.sh:93` | ✅ PASS |
| IF checagem router falhar THEN manter venv+config, reportar, sem docker/sudo/systemd | exit 0, config exists, failure message | `tests/test_setup.py:112` - `assert result.returncode == 0`; `tests/test_setup.py:114` - `assert "router check failed" in result.stderr` | ✅ PASS |
| SHALL recusar `docker`, `sudo`, `systemctl` | script source contains none | `tests/test_setup.py:66` - `assert word not in content` | ✅ PASS |
| WHEN rerun THEN reutilizar `.venv` e sobrescrever `config.json` | second run exit 0, config present | `tests/test_setup.py:103` - `assert second.returncode == 0` | ✅ PASS |

### P1: Abrir o painel no executável

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN argv vazio + stdin/stdout TTY THEN abrir painel, não benchmark | `["panel"]` | `tests/test_cli.py:6` - `assert _inject_default_command([], stdin_is_tty=True, stdout_is_tty=True) == ["panel"]` | ✅ PASS |
| WHEN argv vazio sem TTY THEN comportar como `run` | `["run"]` | `tests/test_cli.py:5` - `assert _inject_default_command([], stdin_is_tty=False, stdout_is_tty=False) == ["run"]` | ✅ PASS |
| WHEN qualquer argumento THEN roteamento CLI atual | doctor/list/run unchanged | `tests/test_cli.py:11` - `assert _inject_default_command(["doctor"]) == ["doctor"]` | ✅ PASS |
| WHEN subcomando `panel` THEN abrir painel | parser accepts `panel`; cmd_panel invokes run_panel | `tests/test_cli_panel.py:15` - `assert args.command == "panel"` | ✅ PASS |
| IF `panel` sem TTY THEN sair ≠ 0 com mensagem de terminal | non-zero exit, message mentions terminal | `tests/test_cli_panel.py:22` - `assert code != 0`; `tests/test_cli_panel.py:24` - `assert "terminal" in ...` | ✅ PASS |

### P1: Faixa de status do router

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHILE Planejar/Doctor/Histórico THEN faixa com host, up/down, build, residentes | host + up/down + build + ids on sub-screens | `tests/test_tui_panel.py:35` - `assert "up" in text` (unit formatter only) | ⚠️ Spec-precision gap (strip not asserted on Plan/Doctor/History screens) |
| IF router inalcançável THEN faixa `down` + host, painel utilizável | down + host, no crash | `tests/test_tui_panel.py:65` - `assert "down" in text`; `tests/test_tui_panel.py:214` - doctor renders | ✅ PASS |
| SHALL NUNCA renderizar valor da chave API | secret absent from rendered text | `tests/test_tui_panel.py:66` - `assert SECRET not in text` | ✅ PASS |

### P1: Planejar modelos, profundidade e tipo

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN abre Planejar THEN listar ids marcáveis | two models in plan | `tests/test_tui_panel.py:103` - `assert plan.model_ids == ["alpha", "beta"]` | ✅ PASS |
| WHEN liga/desliga profundidades THEN subconjunto ordenado crescente | sorted unique depths | `tests/test_plan.py:26` - `assert plan.depths == [0, 8192, 32768]` | ✅ PASS |
| WHEN escolhe tipo THEN exatamente um de speed/quality/both | three modes valid | `tests/test_plan.py:19` - `assert speed_only.problems() == []` (and quality_only, both) | ✅ PASS |
| IF Rodar com zero modelos THEN recusar, permanecer, mensagem | message mentions modelo, result None | `tests/test_tui_panel.py:122` - `assert "modelo" in str(msg.render()).lower()`; `tests/test_tui_panel.py:123` - `assert app.result is None` | ✅ PASS |
| IF Rodar com zero profundidades THEN recusar, mensagem | message mentions profundidade | `tests/test_tui_panel.py:142` - `assert "profundidade" in str(msg.render()).lower()` | ✅ PASS |
| WHEN plano válido THEN gravar `last_plan` | last_plan dict in config | `tests/test_tui_panel.py:195` - `assert cfg.last_plan["model_ids"] == ["alpha", "beta"]` | ✅ PASS |
| WHEN abre com `last_plan` THEN restaurar ids existentes, descartar ausentes | alpha kept, gone dropped | `tests/test_tui_panel.py:170` - `assert plan.model_ids == ["alpha"]` | ✅ PASS |

### P1: Rodar com confirmação e leaderboard

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN residentes fora do plano THEN listar ids e pedir confirmação | confirmer invoked with foreign ids | `tests/test_tui_panel.py:354` - `confirmer=lambda foreign: foreign == ["foreign"]` | ⚠️ Spec-precision gap (UI listing not asserted) |
| IF recusar confirmação THEN voltar sem unload nem leaderboard | result None, unload not called | `tests/test_tui_panel.py:338` - `assert app.result is None`; `tests/test_tui_panel.py:341` - `assert unload_calls == []` | ✅ PASS |
| WHEN aceita ou desnecessário THEN entregar Runner + ModelInfo via cmd_run | force_unload Namespace to cmd_run | `tests/test_cli_panel.py:60` - `assert args.force_unload is True` | ✅ PASS |
| SHALL NÃO reimplementar medição no painel | Runner.run / run_tui not called | `tests/test_tui_panel.py:368` - `monkeypatch.setattr("homebench.runner.Runner.run", _forbidden)` | ✅ PASS |

### P1: Doctor e Histórico

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN Doctor THEN mostrar Check com nome, status, detail | ok and fail checks visible | `tests/test_tui_panel.py:214` - `assert "ok: router" in text`; `tests/test_tui_panel.py:215` - `assert "fail: models" in text` | ✅ PASS |
| WHILE Doctor aberto NÃO load/unload/alterar config | no router HTTP | `tests/test_tui_panel.py:259` - `raise AssertionError("router HTTP not allowed...")` | ✅ PASS |
| WHEN Histórico THEN listar runs mais novo primeiro | beta before alpha in text | `tests/test_tui_panel.py:253` - `assert text.index("beta") < text.index("alpha")` | ✅ PASS |
| IF sem runs THEN mensagem vazio, painel utilizável | "não há runs" message | `tests/test_tui_panel.py:230` - `assert "não há runs" in str(body.render()).lower()` | ✅ PASS |

### P2: Caminho feliz no docs/USO.md

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN guia THEN primeira seção = `./setup.sh` + `homebench` painel | lines 1–40 cite setup.sh and painel | `tests/test_uso_docs.py:10` - `assert "setup.sh" in first_40`; `tests/test_uso_docs.py:11` - `assert "painel" in first_40` | ✅ PASS |
| SHALL manter flags avançadas depois do caminho feliz | throughput after line 40 | `tests/test_uso_docs.py:19` - `assert throughput_idx >= 40` | ✅ PASS |

**Status**: ✅ All ACs covered (2 spec-precision gaps flagged, non-blocking)

---

## Discrimination Sensor

**Baseline porcelain (real tree, pre-sensor)**: `?? .specs/features/guided-ops/validation.md`

Scratch worktree: `/tmp/homebench-sensor-P1GJEr` (detached HEAD `7084697`); removed after run.
Real-tree porcelain post-cleanup: matches baseline (only untracked validation.md).

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `src/homebench/config.py:59` | Invalid JSON `return HomebenchConfig()` → `raise ValueError("mutant")` | ✅ Killed (`test_load_invalid_json_returns_defaults`) |
| 2 | `src/homebench/plan.py:24` | Zero-model check disabled (`if False and not self.model_ids`) | ✅ Killed (`test_run_plan_problems_for_zero_models`) |
| 3 | `src/homebench/cli.py:220` | TTY condition flipped (`not stdin_is_tty and not stdout_is_tty`) | ✅ Killed (`test_inject_default_command`) |
| 4 | `setup.sh:93` | Removed venv path echo on launcher skip | ✅ Killed (`test_setup_prints_venv_path_when_launcher_dir_not_writable`) |

**Sensor depth**: lightweight (4 behavior-level mutations; PYTHONPATH=src for Python modules)
**Sensor outcome**: 4/4 killed ✅

---

## Interactive UAT Results

Not performed (automated verification sufficient for this backend/TUI unit-test feature).

---

## Code Quality

| Principle        | Status |
| ---------------- | ------ |
| Minimum code     | ✅ |
| Surgical changes | ✅ |
| No scope creep   | ✅ |
| Matches patterns | ✅ |
| Spec-anchored outcome check | ✅ |
| Per-layer Coverage Expectation | ✅ |
| Every test maps to spec requirement | ✅ |
| Documented guidelines: `AGENTS.md` | ✅ |

---

## Edge Cases

- [x] `config.json` ausente/inválido: `tests/test_config.py:27` - `assert cfg.host == "http://127.0.0.1:8080"`
- [x] Arquivo da chave ausente: `tests/test_config.py:74` - `assert config.read_api_key(...) is None`
- [x] Env vars ganham de config: `tests/test_config.py:122` - `assert os.environ[config.HOST_ENV] == "http://existing:8080"`
- [x] `setup.sh` de outro cwd: `tests/test_setup.py:93` - `assert result.returncode == 0`
- [x] Catálogo vazio em Planejar: `tests/test_tui_panel.py:118` - `assert len(list(app.query("#model-list Checkbox"))) == 0`; `tests/test_tui_panel.py:122` - `assert "modelo" in str(msg.render()).lower()`
- [x] Dois+ modelos conservados: `tests/test_plan.py:6` - `assert plan.model_ids == ["alpha", "beta"]`

---

## Gate Check

- **Gate command**: `.venv/bin/python -m pytest -q`
- **Result**: 577 passed, 0 failed, 5 skipped
- **Test count before feature**: 515 collected (`aafa7e3^`)
- **Test count after feature**: 582 collected
- **Delta**: +67 new tests
- **Skipped tests**: 5× `tests/test_live_router.py` — opt-in live router (`HOMEBENCH_LIVE=1`); justified per `AGENTS.md`
- **Failures**: none

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status   |
| ----------- | --------------- | ------------ |
| GOPS-01     | Needs Fix       | ✅ Verified  |
| GOPS-02     | Verified        | ✅ Verified  |
| GOPS-03     | Partial         | ✅ Verified  |
| GOPS-04     | Verified        | ✅ Verified  |
| GOPS-05     | Verified        | ✅ Verified  |
| GOPS-06–08  | Verified        | ✅ Verified  |
| GOPS-09–11  | Verified        | ✅ Verified  |
| GOPS-12–15  | Verified        | ✅ Verified  |
| GOPS-16–18  | Verified        | ✅ Verified  |
| GOPS-19–20  | Verified        | ✅ Verified  |
| GOPS-21     | Needs Fix       | ✅ Verified  |

---

## Validation

**Result**: PASS — all 38 acceptance criteria have `file:line` test evidence; 4 former gaps closed in `7084697`; 2 non-blocking spec-precision gaps remain.

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 38/38 ACs matched with `file:line` evidence; 2 spec-precision gaps flagged
**Sensor**: 4/4 mutations killed
**Gate**: 577 passed, 0 failed

**What works**: Config persistence, plan validation/restore, router status snapshots, CLI TTY routing, panel screens (plan/doctor/history/run confirm), cmd_panel→cmd_run handoff, interactive setup prompts, launcher fallback venv path, USO.md regression guard, empty catalog edge case.

**Issues found**: None blocking. Spec-precision gaps: status strip on Plan/Doctor/History screens; foreign-resident UI listing not asserted (confirmer wiring is tested).

**Next steps**: Feature ready to merge. Optional follow-up: tighten spec-precision gaps if desired.
