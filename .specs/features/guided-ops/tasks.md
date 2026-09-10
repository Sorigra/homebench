# Guided Ops Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its
Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is
the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review,
Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

**Execute happens in a new Cursor session.** Workers: Composer 2.5. Do not implement in the
session that only wrote these artifacts.

---

**Design**: `.specs/features/guided-ops/design.md`
**Status**: Draft (aguarda confirmação do operador)

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines found: `AGENTS.md`
> (pytest, `tests/test_<feature>.py`, mock network, Python 3.9–3.12, live tests opt-in,
> never CI; no formatter/linter; no coverage threshold in `pyproject.toml`).
> `CONTRIBUTING.md` ausente. Defaults fortes aplicados em cima do piso do repo.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Domain (`config.py`, `plan.py`, `ops.py`) | unit | All branches; 1:1 to spec ACs; every listed edge case; list-driven flows with **two** items (L-001) | `tests/test_*.py` | `.venv/bin/python -m pytest -q` |
| CLI (`cli.py` inject / `panel`) | unit | Happy + TTY/non-TTY + `panel` sem TTY; `_COMMANDS` inclui `panel` | `tests/test_cli.py`, `tests/test_cli_panel.py` | `.venv/bin/python -m pytest -q` |
| TUI panel (`tui/panel.py`) | unit | `App.run_test`: faixa down, plano, doctor, histórico vazio, recusa AD-002; chave ausente do texto | `tests/test_tui_panel.py` | `.venv/bin/python -m pytest -q` |
| Installer (`setup.sh`) | unit | `--defaults` com HOME isolado; Python &lt; 3.9; router down não desfaz; script sem docker/sudo/systemctl; cwd ≠ repo | `tests/test_setup.py` | `.venv/bin/python -m pytest -q` |
| Docs (`docs/USO.md`) | none | - (build gate only) | - | build gate only |
| Dataclasses / JSON schema | unit | load inválido não crasha; save sem valor de chave | `tests/test_config.py` | `.venv/bin/python -m pytest -q` |

**Nota:** o repo não divide unit/e2e. `quick` e `full` são o mesmo comando. Live router permanece
opt-in e **fora** desta feature (não há GOPS de teste ao vivo).

## Gate Check Commands

> Extraídos de `AGENTS.md` e `pyproject.toml`. Sem linter configurado.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | Depois de qualquer tarefa com testes | `.venv/bin/python -m pytest -q` |
| Full | Idem Quick | `.venv/bin/python -m pytest -q` |
| Build | Ao fechar uma fase ou tarefa só de docs | `.venv/bin/python -m pytest -q` |

---

## Execution Plan

Phases are ordered and run sequentially.

### Phase 1: Config

```
T1 -> T2
```

### Phase 2: Installer

```
T3 -> T4
```

### Phase 3: Plan and snapshots

```
T5 -> T6
T7 -> T8
```

### Phase 4: CLI entry

```
T9 -> T10
```

### Phase 5: Panel TUI

```
T11 -> T12
T11 -> T13
T12 -> T14
```

### Phase 6: Handoff and docs

```
T15 -> T16
```

---

## Task Breakdown

### T1: HomebenchConfig load and save

**What**: Dataclass + `load`/`save` de `$HOMEBENCH_HOME/config.json` com host, `api_key_file`, `model_dir`; JSON ausente ou inválido não levanta.
**Where**: `src/homebench/config.py`
**Depends on**: None
**Reuses**: `history.default_home`
**Requirement**: GOPS-02

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] `save()` grava os três campos e **não** grava chave nem campo `api_key`
- [x] `load()` de arquivo ausente ou JSON inválido devolve config usável, sem exceção
- [x] Testes em `tests/test_config.py`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(config): persist host and key path`

---

### T2: apply_to_environ and read_api_key

**What**: Preencher env vazia a partir do config; env já definida ganha; ler chave do arquivo na hora.
**Where**: `src/homebench/config.py`
**Depends on**: T1
**Reuses**: nomes `LLAMACPP_HOST`, `LLAMACPP_API_KEY`, `HOMEBENCH_MODEL_DIR`
**Requirement**: GOPS-02

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Env vazia recebe host / model_dir / chave lida do arquivo
- [x] Env já definida não é sobrescrita
- [x] Arquivo da chave ausente ⇒ `LLAMACPP_API_KEY` não é setada
- [x] Valor da chave não aparece no JSON salvo
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(config): apply file settings to empty env`

---

### T3: setup.sh --defaults happy path

**What**: Script na raiz: Python 3.9+, `.venv`, `pip install -e .` (salvo skip de teste), grava config com os três defaults, tenta lançador.
**Where**: `setup.sh`
**Depends on**: T2
**Reuses**: `config.save` via `.venv/bin/python` depois do install
**Requirement**: GOPS-01, GOPS-02, GOPS-03, GOPS-05

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] `--defaults` usa host `http://127.0.0.1:8080`, `~/llm-server/llama/api-key.txt`, `/home/eskudo/ai-models`
- [x] Fonte do script não contém `docker`, `sudo` nem `systemctl`
- [x] `HOMEBENCH_SETUP_SKIP_PIP=1` ainda grava `config.json` (pytest rápido); sem a flag, chama `pip install -e .`
- [x] Testes em `tests/test_setup.py` com `HOME`/`HOMEBENCH_HOME` isolados
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(setup): add noninteractive installer`

---

### T4: setup.sh failure and idempotent paths

**What**: Python &lt; 3.9 aborta; router down não desfaz; `~/.local/bin` falha com aviso e exit 0; rerun reusa venv; opera no dir do script.
**Where**: `setup.sh`
**Depends on**: T3
**Reuses**: `homebench doctor` de leitura após install (pode falhar)
**Requirement**: GOPS-01, GOPS-03, GOPS-04, GOPS-05

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Fake `python3` 3.8 no PATH ⇒ exit ≠ 0 e sem `.venv`
- [x] Doctor/router fail ⇒ exit 0 se venv+config existem; nenhum docker
- [x] Segundo run `--defaults` não falha
- [x] Invocar via path absoluto a partir de outro cwd grava no repo do script
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `fix(setup): keep install when router is down`

---

### T5: RunPlan validation

**What**: `RunPlan` com ids, depths em `{0,8192,32768}`, tipo exclusivo; `problems()` cobre GOPS-13.
**Where**: `src/homebench/plan.py`
**Depends on**: None
**Reuses**: nenhum
**Requirement**: GOPS-12, GOPS-13

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Dois model ids sobrevivem em `model_ids` (não só o primeiro)
- [x] Zero modelos ou zero depths ⇒ `problems()` não vazio
- [x] Os três tipos (só speed, só quality, ambos) são representáveis; default só speed
- [x] Depths gravados ordenados e únicos
- [x] Testes em `tests/test_plan.py`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(plan): add validatable run plan`

---

### T6: last_plan persist and restore

**What**: `to_dict`/`from_dict`/`restore(saved, available_ids)` ligado a `HomebenchConfig.last_plan`.
**Where**: `src/homebench/plan.py`
**Depends on**: T1, T5
**Reuses**: `config.save` / `load`
**Requirement**: GOPS-14, GOPS-15

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Restore com dois ids disponíveis devolve os dois
- [x] Id ausente do catálogo é descartado
- [x] Depth fora de `DEPTH_CHOICES` é descartado
- [x] Round-trip via `config.json`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(plan): restore last plan dropping stale ids`

---

### T7: router_status snapshot

**What**: `RouterStatus` via `LlamaRouterClient`; down/401 não crasha; `error` sem valor da chave.
**Where**: `src/homebench/ops.py`
**Depends on**: None
**Reuses**: `lifecycle/router.py`, `ProviderError`
**Requirement**: GOPS-09, GOPS-10, GOPS-11

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Router up: host, `reachable=True`, `build_info`, **dois** residentes
- [x] Rede caída / 401: `reachable=False`, painel-consumível, secret `sk-secret` não está em `error`
- [x] Testes `pytest-httpx` em `tests/test_ops.py`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(ops): snapshot router status without crashing`

---

### T8: doctor and history snapshots

**What**: `doctor_snapshot()` e `history_snapshot()` delegando aos módulos existentes.
**Where**: `src/homebench/ops.py`
**Depends on**: T7
**Reuses**: `doctor.run_checks`, `history.list_runs`
**Requirement**: GOPS-19, GOPS-20

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Snapshot de doctor com **dois** `Check` (ok e fail) preserva ambos
- [x] Histórico vazio = lista vazia, sem exceção
- [x] **Dois** runs: mais novo primeiro
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(ops): expose doctor and history snapshots`

---

### T9: inject panel on TTY empty argv

**What**: `_inject_default_command` ganha override de TTY; vazio+TTY ⇒ `panel`; vazio sem TTY ⇒ `run`; `_COMMANDS` inclui `panel`.
**Where**: `src/homebench/cli.py`
**Depends on**: None
**Reuses**: `_COMMANDS`, testes atuais de inject
**Requirement**: GOPS-06, GOPS-07, GOPS-08

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] `([], stdin_is_tty=False, stdout_is_tty=False) == ["run"]` (pytest/CI)
- [x] `([], stdin_is_tty=True, stdout_is_tty=True) == ["panel"]`
- [x] `["doctor"]` e `["run", "--no-tui"]` inalterados
- [x] `"panel"` ∈ `_COMMANDS`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): open panel when argv is empty on a TTY`

---

### T10: panel subcommand and apply config in main

**What**: Subparser `panel`; `main` chama `apply_to_environ(load())`; `panel` sem TTY sai ≠ 0 com mensagem.
**Where**: `src/homebench/cli.py`
**Depends on**: T2, T9
**Reuses**: `config.load`, `apply_to_environ`
**Requirement**: GOPS-06, GOPS-08

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] `build_parser` aceita `panel`
- [x] `cmd_panel` sem TTY retorna ≠ 0 e menciona terminal
- [x] `main` aplica config: env vazia recebe host do arquivo (teste com HOME isolado)
- [x] Testes em `tests/test_cli_panel.py`
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): add panel command and load config`

---

### T11: Panel shell and status strip

**What**: App Textual com faixa sempre visível nas telas do menu; `run_panel()`; `q` sai devolvendo `None`.
**Where**: `src/homebench/tui/panel.py`
**Depends on**: T7, T10
**Reuses**: `ops.router_status`, padrão `tests/test_tui.py`
**Requirement**: GOPS-09, GOPS-10, GOPS-11

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Faixa mostra host e `down` quando o snapshot está down; App não crasha
- [x] Secret `sk-secret` não aparece no texto renderizado
- [x] `q` encerra com `None`
- [x] Testes `run_test` em `tests/test_tui_panel.py`
- [x] `config.py`/`plan.py`/`ops.py` não importam `tui` (teste de import)
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(tui): add BIOS panel status strip`

---

### T12: Plan screen

**What**: Tela Planejar: toggles de modelos (dois+), depths, tipo de teste; recusa Rodar inválido; grava `last_plan`.
**Where**: `src/homebench/tui/panel.py`
**Depends on**: T5, T6, T11
**Reuses**: `RunPlan.problems`, `restore`
**Requirement**: GOPS-12, GOPS-13, GOPS-14, GOPS-15

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [x] Dois modelos marcáveis; os dois entram no plano
- [x] Rodar com zero modelos ou zero depths não encerra o App e mostra a recusa
- [x] Plano válido persiste em `config.json` e restaura ids ainda existentes
- [x] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(tui): plan models depths and test type`

---

### T13: Doctor and History screens

**What**: Telas só leitura Doctor e Histórico; histórico vazio mostra mensagem.
**Where**: `src/homebench/tui/panel.py`
**Depends on**: T8, T11
**Reuses**: `ops.doctor_snapshot`, `ops.history_snapshot`
**Requirement**: GOPS-19, GOPS-20

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [ ] Doctor mostra **dois** checks (ok e fail)
- [ ] Histórico vazio: mensagem, sem exceção
- [ ] Nenhum `load`/`unload` HTTP disparado ao abrir as telas
- [ ] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(tui): show doctor and history screens`

---

### T14: Run confirmation inside the panel

**What**: Rodar com plano válido: se há residentes fora do plano, pedir sim/não; não ⇒ permanece e não unloada; sim ⇒ `app.exit(plan)`.
**Where**: `src/homebench/tui/panel.py`
**Depends on**: T12
**Reuses**: lista de residentes de `router_status`; **não** chama `HomebenchApp`
**Requirement**: GOPS-16, GOPS-17, GOPS-18

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [ ] Confirmer false: App continua; `unload` não é chamado
- [ ] Confirmer true (ou zero estrangeiros): `run_panel()` devolve o `RunPlan`
- [ ] Painel não chama `Runner.run`
- [ ] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(tui): confirm unload before leaving the panel`

---

### T15: cmd_panel hands off to cmd_run

**What**: Se `run_panel()` devolve plano, montar `Namespace` e chamar `cmd_run` com `force_unload=True` e depths/modelos/tipo do plano.
**Where**: `src/homebench/cli.py`
**Depends on**: T10, T14
**Reuses**: `cmd_run`, `_select_models`
**Requirement**: GOPS-18, GOPS-16

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [ ] `run_panel` None ⇒ `cmd_run` não é chamado, exit 0
- [ ] Plano só-speed ⇒ `no_quality=True`, `no_speed=False`; ids viram `-m`
- [ ] `force_unload=True` no Namespace (confirmação já feita)
- [ ] Teste com `run_panel` monkeypatch; FakeProvider; **não** precisa TTY real
- [ ] Gate: `.venv/bin/python -m pytest -q` exit 0

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): run confirmed panel plan via existing runner`

---

### T16: Lead docs/USO.md with setup and panel

**What**: Primeira seção de uso = `./setup.sh` + `homebench` no TTY; flags avançadas depois.
**Where**: `docs/USO.md`
**Depends on**: T15
**Reuses**: nenhum
**Requirement**: GOPS-21

**Tools**: MCP: NONE · Skill: tlc-spec-driven

**Done when**:
- [ ] Primeiras 40 linhas citam `setup.sh` e o painel
- [ ] `throughput` aparece só depois dessa seção
- [ ] Gate: `.venv/bin/python -m pytest -q` exit 0 (anti-regressão)

**Tests**: none
**Gate**: build
**Commit**: `docs(uso): lead with setup.sh and the panel`

---

## Phase Execution Map

```
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6

T1 -> T2
T2 -> T3
T3 -> T4
T5 -> T6
T1 -> T6
T7 -> T8
T9 -> T10
T2 -> T10
T10 -> T11
T7 -> T11
T11 -> T12
T5 -> T12
T6 -> T12
T11 -> T13
T8 -> T13
T12 -> T14
T14 -> T15
T10 -> T15
T15 -> T16
```

Execution is strictly sequential. ~16 tasks ⇒ dois batches de ~7–8 (Phase 1–3, depois 4–6) ou
três batches (1–2, 3–4, 5–6). Nunca partir uma fase. Workers: Composer 2.5, sessão nova.

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1: config load/save | 1 module | Granular |
| T2: apply_to_environ | 1 function set, same file | Granular |
| T3: setup.sh happy | 1 script | Granular |
| T4: setup.sh failures | same script, cohesive | Granular |
| T5: RunPlan | 1 module | Granular |
| T6: last_plan restore | same module | Granular |
| T7: router_status | 1 function | Granular |
| T8: doctor/history snapshots | same module, two functions | OK cohesive |
| T9: inject default | 1 function | Granular |
| T10: panel subcommand | same CLI file | Granular |
| T11: panel shell | 1 App | Granular |
| T12: plan screen | same App | Granular |
| T13: doctor/history screens | same App | Granular |
| T14: run confirm | same App | Granular |
| T15: cmd_panel handoff | 1 CLI function | Granular |
| T16: USO.md | 1 doc | Granular |

**Granularity check**: no task `Where` names two files.

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | (entry) | Match |
| T2 | T1 | T1 -> T2 | Match |
| T3 | T2 | T2 -> T3 | Match |
| T4 | T3 | T3 -> T4 | Match |
| T5 | None | (entry) | Match |
| T6 | T1, T5 | T1 -> T6, T5 -> T6 | Match |
| T7 | None | (entry) | Match |
| T8 | T7 | T7 -> T8 | Match |
| T9 | None | (entry) | Match |
| T10 | T2, T9 | T2 -> T10, T9 -> T10 | Match |
| T11 | T7, T10 | T7 -> T11, T10 -> T11 | Match |
| T12 | T5, T6, T11 | T5 -> T12, T6 -> T12, T11 -> T12 | Match |
| T13 | T8, T11 | T8 -> T13, T11 -> T13 | Match |
| T14 | T12 | T12 -> T14 | Match |
| T15 | T10, T14 | T10 -> T15, T14 -> T15 | Match |
| T16 | T15 | T15 -> T16 | Match |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Domain config | unit | unit | OK |
| T2 | Domain config | unit | unit | OK |
| T3 | Installer | unit | unit | OK |
| T4 | Installer | unit | unit | OK |
| T5 | Domain plan | unit | unit | OK |
| T6 | Domain plan | unit | unit | OK |
| T7 | Domain ops | unit | unit | OK |
| T8 | Domain ops | unit | unit | OK |
| T9 | CLI | unit | unit | OK |
| T10 | CLI | unit | unit | OK |
| T11 | TUI panel | unit | unit | OK |
| T12 | TUI panel | unit | unit | OK |
| T13 | TUI panel | unit | unit | OK |
| T14 | TUI panel | unit | unit | OK |
| T15 | CLI | unit | unit | OK |
| T16 | Docs | none | none | OK |
