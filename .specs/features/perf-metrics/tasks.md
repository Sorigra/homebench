# Métricas de Performance Bruta Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/perf-metrics/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `AGENTS.md` (raiz, via `CLAUDE.md`), `pyproject.toml` (`[dev]` extra), `.github/workflows/ci.yml`. Nenhum linter/formatter está configurado no projeto — `AGENTS.md` diz explicitamente "There is no linter or formatter configured — match surrounding style", então o gate Build é `pytest` + `python -m build` + `twine check`, sem passo de lint.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Dataclasses de resultado (`models.py`) | unit | Round-trip `to_dict`/`from_dict`, incluindo carga de run antigo sem os campos novos | `tests/test_runner_report.py`, `tests/test_history.py` | `.venv/bin/python -m pytest -q` |
| Providers HTTP (`providers/*.py`) | unit (nível HTTP, `pytest-httpx`) | Todas as ACs do provider 1:1 + todo edge case listado; nunca toca rede real | `tests/test_providers.py`, `tests/test_llamacpp_router.py` | `.venv/bin/python -m pytest -q` |
| Lógica de medição (`metrics/depth.py`) | unit | Todos os ramos; 1:1 com as ACs de PERF-10..14; todo edge case listado | `tests/test_depth_*.py` (novo, seguindo `tests/test_throughput.py`) | `.venv/bin/python -m pytest -q` |
| Orquestração (`runner.py`) | unit (com `FakeProvider`) | Caminho feliz + isolamento de erro por modelo + compat de `speed` | `tests/test_runner_*.py` | `.venv/bin/python -m pytest -q` |
| Renderizadores (`report.py`, `plainui.py`, `tui/app.py`) | unit | Linhas por profundidade em cada formato + célula `–` para prefill ausente | `tests/test_reports.py`, `tests/test_tui.py` | `.venv/bin/python -m pytest -q` |
| CLI (`cli.py`) | unit | Flag válida, flag inválida aborta antes de tocar modelo | `tests/test_cli.py` | `.venv/bin/python -m pytest -q` |
| Integração ao vivo (`tests/test_live_router.py`) | none | Desligado por padrão (`HOMEBENCH_LIVE=1`), nunca no CI | `tests/test_live_router.py` | fora do gate |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | Depois de tarefas com testes unitários do módulo tocado | `.venv/bin/python -m pytest -q tests/<arquivo-alvo>.py` |
| Full | Depois de tarefas que cruzam camadas (provider + runner + saída) | `.venv/bin/python -m pytest -q` |
| Build | Fim de fase e antes de fechar a feature | `.venv/bin/python -m pytest -q && .venv/bin/python -m build && .venv/bin/twine check dist/*` |

**Linha de base:** 378 testes coletados hoje (373 passam, 5 pulados — os `HOMEBENCH_LIVE`). Nenhuma tarefa pode reduzir esse número.

---

## Execution Plan

Phases are ordered and run sequentially - each phase completes before the next begins, and tasks within a phase execute in order.

### Phase 1: Forma do resultado

```
T1 → T2
T3
```

### Phase 2: Camada de provider

```
T4 → T5 → T6 → T7
```

### Phase 3: Medição por profundidade

```
T8 → T9 → T10 → T11
```

### Phase 4: Superfícies de saída

```
T12 → T13
T12 → T14
T12 → T15
T16
```

### Phase 5: Compatibilidade e documentação

```
T17
```

---

## Task Breakdown

### T1: Campos novos em `SpeedMetrics` ✅ Complete

**What**: adicionar `content_tokens`, `reasoning_tokens`, `prefill_tps: Optional[float]` e `timings_source` ao dataclass, com defaults que preservem `from_dict` de runs antigos.
**Where**: `src/homebench/models.py`
**Depends on**: None
**Reuses**: `_pick()` em `models.py` (já ignora chaves desconhecidas)
**Requirement**: PERF-03, PERF-16

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Os quatro campos existem com default e `to_dict` os inclui
- [x] `from_dict` de um payload sem os campos novos devolve os defaults
- [x] `prefill_tps` aceita `None` e sobrevive ao round-trip
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_runner_report.py`
- [x] Test count: 378 + 3 novos = 381 testes passam (nenhuma deleção silenciosa)

**Tests**: unit
**Gate**: quick
**Commit**: `feat(models): add reasoning, prefill and timings-source fields to SpeedMetrics`

---

### T2: `DepthMetrics` e `ModelReport.depth_results` ✅ Complete

**What**: criar o dataclass `DepthMetrics` conforme o design e pendurá-lo em `ModelReport` como lista, com `to_dict`/`from_dict`.
**Where**: `src/homebench/models.py`
**Depends on**: T1
**Reuses**: molde de `ConcurrencyPoint` em `metrics/throughput.py:47`
**Requirement**: PERF-13, PERF-16

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `DepthMetrics` tem os 9 campos do design, com `prefill_tps` e `skipped` opcionais
- [x] `ModelReport.depth_results` faz round-trip completo
- [x] Um JSON de run salvo **antes** da feature carrega com `depth_results == []`
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_runner_report.py tests/test_history.py`
- [x] Test count: 381 + 4 = 385 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(models): add DepthMetrics and ModelReport.depth_results`

---

### T3: `parse_depths()` ✅ Complete

**What**: criar o módulo `metrics/depth.py` com só a função de parsing da spec `--depths`.
**Where**: `src/homebench/metrics/depth.py`
**Depends on**: None
**Reuses**: forma de `throughput.parse_levels` (`metrics/throughput.py:28`)
**Requirement**: PERF-11

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `"0,8192,32768"` → `[0, 8192, 32768]`, **preservando a ordem dada** (diferente de `parse_levels`, que ordena)
- [x] Não deduplica (edge case da spec)
- [x] `""` e `","` → `[0]`
- [x] Valor não inteiro ou negativo levanta `ValueError` citando o valor
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_depth_prompt.py`
- [x] Test count: 385 + 6 = 391 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(metrics): add parse_depths for the --depths spec`

---

### T4: Contar `reasoning_content` no stream ✅ Complete

**What**: no parser de SSE, acumular `delta.reasoning_content` separado de `delta.content`, disparar o TTFT no primeiro token de qualquer um dos dois e preencher as contagens.
**Where**: `src/homebench/providers/openai_compat.py`
**Depends on**: T1
**Reuses**: laço de SSE existente em `generate()`; `GenerationResult` em `providers/base.py`
**Requirement**: PERF-01, PERF-02, PERF-03, PERF-04

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Stream 100% `reasoning_content` produz `tokens_per_sec > 0` e `ttft_s > 0`
- [x] `GenerationResult.text` contém **apenas** `content` (PERF-04)
- [x] `content_tokens` e `reasoning_tokens` refletem os deltas de cada tipo
- [x] Stream misto (`content` + `reasoning_content`) conta os dois no tempo de decode
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_providers.py`
- [x] Test count: 391 + 5 = 396 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `fix(providers): count reasoning_content tokens in speed timings`

---

### T5: Ler o `timings` do servidor ✅ Complete

**What**: extrair `prompt_per_second`, `predicted_per_second`, `prompt_ms`, `prompt_n` e `cache_n` do chunk final, com fallback para cronometragem no cliente.
**Where**: `src/homebench/providers/openai_compat.py`
**Depends on**: T4
**Reuses**: o mesmo laço de SSE; campo `prompt_eval_s` já declarado em `SpeedMetrics`
**Requirement**: PERF-06, PERF-07, PERF-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Com `timings` presente: `prefill_tps` e `tokens_per_sec` vêm do servidor e `timings_source == "server"`
- [x] Sem `timings`: `tokens_per_sec` vem do cliente, `prefill_tps is None`, `timings_source == "client"`
- [x] `prompt_eval_s` recebe `prompt_ms / 1000` (campo que hoje nunca é escrito)
- [x] `cache_n` é preservado para o chamador
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_providers.py tests/test_llamacpp_router.py`
- [x] Test count: 396 + 5 = 401 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(providers): use server-side timings for prefill and decode rates`

---

### T6: Parâmetro `cache_prompt` em `generate()` ✅ Complete

**What**: aceitar `cache_prompt: bool = True` em `Provider.generate` e enviá-lo no corpo da requisição OpenAI-compatível.
**Where**: `src/homebench/providers/base.py`, `src/homebench/providers/openai_compat.py`
**Depends on**: T5
**Reuses**: assinatura de `generate()` já existente (parâmetros keyword-only)
**Requirement**: PERF-13

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `cache_prompt=False` aparece no corpo JSON enviado
- [x] Default `True` não altera o corpo em relação a hoje (nenhuma regressão nos providers existentes)
- [x] `FakeProvider` e os demais providers aceitam o parâmetro sem quebrar
- [x] Gate check passes: `.venv/bin/python -m pytest -q`
- [x] Test count: 401 + 3 = 404 testes passam

**Tests**: unit
**Gate**: full
**Commit**: `feat(providers): add cache_prompt control to generate()`

---

### T7: `Provider.tokenize()` e a implementação llama.cpp ✅ Complete

**What**: capacidade opcional `tokenize(model, text) -> Optional[int]`, default `None` na base, implementada no `LlamaCppProvider` via `POST /tokenize`.
**Where**: `src/homebench/providers/base.py`, `src/homebench/providers/llamacpp.py`
**Depends on**: T6
**Reuses**: `_headers()` de `OpenAICompatibleProvider`; padrão de erro de `lifecycle/router.py:62`
**Requirement**: PERF-12 (suporte)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Base devolve `None` (nunca uma estimativa disfarçada)
- [x] llama.cpp devolve `len(resposta["tokens"])` — formato verificado ao vivo
- [x] 404, 400 ou erro de rede devolvem `None` em vez de levantar
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_llamacpp_router.py tests/test_providers.py`
- [x] Test count: 404 + 4 = 408 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(providers): add optional tokenize() capability with llama.cpp support`

---

### T8: `build_context_prompt()` ✅ Complete

**What**: sintetizar um prompt na profundidade alvo, exato via tokenizer injetado ou estimado quando não houver.
**Where**: `src/homebench/metrics/depth.py`
**Depends on**: T3
**Reuses**: nada; lógica nova. Tokenizer entra **injetado** (callable), não como import de provider
**Requirement**: PERF-12

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Com tokenizer: a contagem devolvida bate exatamente com o alvo
- [x] Sem tokenizer (`None`): devolve texto e contagem `None`, sem levantar
- [x] Alvo `0` devolve o prompt curto de velocidade, não texto de filler
- [x] Lida com o offset de BOS (medido: 1 unidade = 11 tokens, 100 = 1001)
- [x] Não faz nenhuma chamada de rede própria (tokenizer é injetado)
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_depth_prompt.py`
- [x] Test count: 408 + 6 = 414 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(metrics): synthesise context prompts at a target token depth`

---

### T9: `measure_at_depths()` ✅ Complete

**What**: rodar a medição em cada profundidade, com `cache_prompt=False`, repetição dentro da profundidade, e pular profundidade quando o contexto estoura.
**Where**: `src/homebench/metrics/depth.py`
**Depends on**: T8
**Reuses**: lógica "repete `cfg.repeat` e fica com o melhor" hoje em `runner._measure_speed:218`
**Requirement**: PERF-10, PERF-13, PERF-14

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Devolve um `DepthMetrics` por profundidade pedida, na ordem dada
- [x] `depth_actual` vem do `prompt_n` do servidor, nunca do alvo pedido
- [x] `ProviderError` de contexto excedido → `skipped` preenchido e as demais profundidades seguem
- [x] Qualquer outro `ProviderError` **sobe** (preserva MLC-11)
- [x] `cache_n > 0` gera aviso, sem descartar a medição
- [x] `--repeat > 1` repete dentro de cada profundidade, não a varredura inteira
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_depth_measure.py`
- [x] Test count: 414 + 9 = 423 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(metrics): measure speed across context depths`

---

### T10: Ligar a varredura no `Runner` ✅ Complete

**What**: `RunConfig.depths`, `_measure_speed` delegando a `measure_at_depths`, e `ModelReport.speed` recebendo o ponto da menor profundidade.
**Where**: `src/homebench/runner.py`
**Depends on**: T9, T2
**Reuses**: `RunConfig.to_dict`, evento `EV_PHASE` para progresso por profundidade
**Requirement**: PERF-10, PERF-15

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `RunConfig.depths` default `[0, 8192, 32768]` e aparece em `to_dict`
- [x] `ModelReport.speed` é o ponto da menor profundidade medida (compat de `score.py` e `diff`)
- [x] `EV_PHASE` emite a profundidade corrente para a TUI
- [x] Erro num modelo não contamina os outros (regressão de `test_runner_error_isolation.py`)
- [x] Gate check passes: `.venv/bin/python -m pytest -q`
- [x] Test count: 423 + 5 = 428 testes passam

**Tests**: unit
**Gate**: full
**Commit**: `feat(runner): sweep context depths during the speed probe`

---

### T11: Aviso de geração vazia ✅ Complete

**What**: quando uma geração termina sem nenhum token em `content` e em `reasoning_content`, registrar aviso em `ModelReport.warnings`.
**Where**: `src/homebench/runner.py`
**Depends on**: T10
**Reuses**: `ModelReport.warnings` e o evento `phase="warning"` criados em MLC-14
**Requirement**: PERF-05

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Geração sem token nenhum produz aviso identificando modelo e profundidade
- [x] O aviso persiste no JSON salvo e reaparece depois do leaderboard
- [x] Geração só com `reasoning_content` **não** dispara o aviso
- [x] Gate check passes: `.venv/bin/python -m pytest -q tests/test_runner_unload_warning.py tests/test_runner_report.py`
- [x] Test count: 428 + 3 = 431 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(runner): warn when a generation produces no tokens at all`

---

### T12: `leaderboard_rows()` e a tabela Rich

**What**: helper único que expande `ModelReport` em linhas (uma por profundidade) e a tabela Rich do relatório final consumindo-o, com colunas Depth / Prefill / Decode.
**Where**: `src/homebench/report.py`
**Depends on**: T10
**Reuses**: `fmt_tps`, `fmt_ttft`, `fmt_bytes` já em `report.py`
**Requirement**: PERF-09, PERF-17

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Modelo com 3 profundidades gera 3 linhas; modelo sem `depth_results` gera 1 linha sem profundidade
- [ ] `prefill_tps is None` renderiza `–`, nunca `0.00`
- [ ] Ordenação do leaderboard usa o decode da menor profundidade
- [ ] Profundidade pulada aparece com o motivo
- [ ] Gate check passes: `.venv/bin/python -m pytest -q tests/test_reports.py`
- [ ] Test count: 431 + 6 = 437 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(report): one leaderboard row per model and context depth`

---

### T13: Markdown, JSON e HTML

**What**: os três exportadores consumindo `leaderboard_rows()` para não divergirem do terminal.
**Where**: `src/homebench/report.py`
**Depends on**: T12
**Reuses**: `leaderboard_rows()` de T12; os templates de export já existentes
**Requirement**: PERF-17

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] O cabeçalho Markdown traz as colunas novas e uma linha por profundidade
- [ ] O HTML idem, com a barra de proporção calibrada pelo decode
- [ ] O JSON exporta `depth_results` completo
- [ ] Gate check passes: `.venv/bin/python -m pytest -q tests/test_reports.py`
- [ ] Test count: 437 + 4 = 441 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(report): render depth rows in markdown, json and html exports`

---

### T14: Tabela ao vivo do `plainui`

**What**: o renderizador Rich não-TUI mostrando profundidade, prefill e decode, e o progresso por profundidade.
**Where**: `src/homebench/plainui.py`
**Depends on**: T12
**Reuses**: `leaderboard_rows()`; assinatura de observer já existente
**Requirement**: PERF-17

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Colunas novas presentes na tabela ao vivo
- [ ] O evento `EV_PHASE` com profundidade aparece na coluna Status
- [ ] Gate check passes: `.venv/bin/python -m pytest -q tests/test_reports.py tests/test_cli.py`
- [ ] Test count: 441 + 3 = 444 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(plainui): show depth, prefill and decode in the live table`

---

### T15: Tabela da TUI Textual

**What**: mesma mudança de colunas em `tui/app.py`.
**Where**: `src/homebench/tui/app.py`
**Depends on**: T12
**Reuses**: `leaderboard_rows()`; teste `tests/test_tui.py` já existente
**Requirement**: PERF-17

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Colunas novas presentes e preenchidas
- [ ] `test_tui_runs_and_fills_leaderboard` segue passando com as linhas por profundidade
- [ ] Gate check passes: `.venv/bin/python -m pytest -q tests/test_tui.py`
- [ ] Test count: 444 + 2 = 446 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(tui): show depth, prefill and decode in the leaderboard`

---

### T16: Flag `--depths` na CLI

**What**: expor a flag no subcomando `run`, validando antes de tocar em qualquer modelo.
**Where**: `src/homebench/cli.py`
**Depends on**: T10
**Reuses**: `parse_depths()` de T3; padrão de flags do argparse já em `cli.py`
**Requirement**: PERF-11

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `--depths 0` reproduz o comportamento anterior à feature
- [ ] `--depths 0,8192,32768` é o default quando a flag é omitida
- [ ] Valor inválido aborta com mensagem citando o valor, **antes** de qualquer carga de modelo
- [ ] `--help` documenta a flag
- [ ] Gate check passes: `.venv/bin/python -m pytest -q tests/test_cli.py tests/test_cli_lifecycle.py`
- [ ] Test count: 446 + 5 = 451 testes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): add --depths to select the context depths to measure`

---

### T17: Compatibilidade de histórico e documentação

**What**: teste de regressão carregando um run real salvo antes da feature, mais a atualização de `docs/USO.md` e `README.md`.
**Where**: `tests/test_history.py`, `docs/USO.md`, `README.md`
**Depends on**: T13, T14, T15, T16, T11
**Reuses**: fixtures de `tests/test_history.py`
**Requirement**: PERF-16, PERF-17

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Um JSON de run pré-feature carrega, lista em `history` e compara em `diff`
- [ ] `USO.md` §8 corrigido: `reasoning_content` **zerava** o tok/s, não "subestimava"
- [ ] `USO.md` ganha a seção de `--depths` com o custo de tempo do padrão
- [ ] README documenta as colunas novas
- [ ] Gate check passes: `.venv/bin/python -m pytest -q && .venv/bin/python -m build && .venv/bin/twine check dist/*`
- [ ] Test count: 451 + 3 = 454 testes passam, 5 pulados

**Tests**: unit
**Gate**: build
**Commit**: `docs(perf-metrics): document depth sweep and correct the reasoning_content note`

---

## Phase Execution Map

Execução estritamente sequencial: uma tarefa por vez, na ordem, dentro de cada fase.

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
```

Arestas entre fases (cada uma corresponde a um `Depends on` de tarefa):

```
T1 → T4
T3 → T8
T2 → T10
T10 → T12
T10 → T16
T11 → T17
T13 → T17
T14 → T17
T15 → T17
T16 → T17
```

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: campos em `SpeedMetrics` | 1 dataclass | ✅ Granular |
| T2: `DepthMetrics` + campo em `ModelReport` | 2 dataclasses coesos, 1 arquivo | ✅ Granular |
| T3: `parse_depths` | 1 função | ✅ Granular |
| T4: `reasoning_content` no parser | 1 função (`generate`) | ✅ Granular |
| T5: `timings` do servidor | mesma função, aspecto distinto | ✅ Granular |
| T6: `cache_prompt` | 1 parâmetro, 2 arquivos (base + impl) | ✅ Granular |
| T7: `tokenize()` | 1 método, 2 arquivos (base + impl) | ✅ Granular |
| T8: `build_context_prompt` | 1 função | ✅ Granular |
| T9: `measure_at_depths` | 1 função | ✅ Granular |
| T10: wiring no `Runner` | 1 arquivo | ✅ Granular |
| T11: aviso de geração vazia | 1 comportamento | ✅ Granular |
| T12: `leaderboard_rows` + tabela Rich | 1 helper + seu 1º consumidor | ✅ Granular |
| T13: markdown/json/html | 3 exportadores, 1 arquivo, mesma mudança | ⚠️ Coeso — OK |
| T14: `plainui` | 1 arquivo | ✅ Granular |
| T15: `tui` | 1 arquivo | ✅ Granular |
| T16: `--depths` | 1 flag | ✅ Granular |
| T17: compat + docs | 1 teste + 2 docs | ⚠️ Coeso — OK |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | sem seta de entrada (raiz) | ✅ Match |
| T2 | T1 | `T1 → T2` (Phase 1) | ✅ Match |
| T3 | None | sem seta de entrada (raiz) | ✅ Match |
| T4 | T1 | `T1 → T4` (arestas entre fases) | ✅ Match |
| T5 | T4 | `T4 → T5` (Phase 2) | ✅ Match |
| T6 | T5 | `T5 → T6` (Phase 2) | ✅ Match |
| T7 | T6 | `T6 → T7` (Phase 2) | ✅ Match |
| T8 | T3 | `T3 → T8` (arestas entre fases) | ✅ Match |
| T9 | T8 | `T8 → T9` (Phase 3) | ✅ Match |
| T10 | T9, T2 | `T9 → T10` (Phase 3), `T2 → T10` (entre fases) | ✅ Match |
| T11 | T10 | `T10 → T11` (Phase 3) | ✅ Match |
| T12 | T10 | `T10 → T12` (arestas entre fases) | ✅ Match |
| T13 | T12 | `T12 → T13` (Phase 4) | ✅ Match |
| T14 | T12 | `T12 → T14` (Phase 4) | ✅ Match |
| T15 | T12 | `T12 → T15` (Phase 4) | ✅ Match |
| T16 | T10 | `T10 → T16` (arestas entre fases) | ✅ Match |
| T17 | T11, T13, T14, T15, T16 | as cinco setas `→ T17` (entre fases) | ✅ Match |

Paridade total: cada `Depends on` tem uma seta e cada seta tem um `Depends on`. Nenhuma
dependência aponta para fase posterior.

**Avisos aceitos do validador** (WARN, não bloqueiam): T6, T7 e T17 nomeiam mais de um arquivo
em `Where`. São coesos por construção — T6 e T7 adicionam uma capacidade opcional, que exige o
default na classe base **e** a implementação concreta no mesmo commit para não deixar contrato
sem implementação; T17 é um teste de regressão mais os dois documentos que ele torna verdadeiros.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Dataclasses de resultado | unit | unit | ✅ OK |
| T2 | Dataclasses de resultado | unit | unit | ✅ OK |
| T3 | Lógica de medição | unit | unit | ✅ OK |
| T4 | Providers HTTP | unit | unit | ✅ OK |
| T5 | Providers HTTP | unit | unit | ✅ OK |
| T6 | Providers HTTP | unit | unit | ✅ OK |
| T7 | Providers HTTP | unit | unit | ✅ OK |
| T8 | Lógica de medição | unit | unit | ✅ OK |
| T9 | Lógica de medição | unit | unit | ✅ OK |
| T10 | Orquestração | unit | unit | ✅ OK |
| T11 | Orquestração | unit | unit | ✅ OK |
| T12 | Renderizadores | unit | unit | ✅ OK |
| T13 | Renderizadores | unit | unit | ✅ OK |
| T14 | Renderizadores | unit | unit | ✅ OK |
| T15 | Renderizadores | unit | unit | ✅ OK |
| T16 | CLI | unit | unit | ✅ OK |
| T17 | Dataclasses (regressão) + docs | unit | unit | ✅ OK |

Nenhum `Tests: none`. Nenhuma violação.
