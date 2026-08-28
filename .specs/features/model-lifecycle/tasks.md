# Model Lifecycle Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its
Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is
the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review,
Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/model-lifecycle/design.md`
**Status**: Approved (usuário aprovou em 2026-08-28; `validate_tasks.py` → 0 erros)

**Precondição de ambiente (já satisfeita):** `.venv/` criado com `python3 -m venv .venv` e
`.venv/bin/python -m pip install -e ".[dev]"`. Verificado em 2026-08-28: **162 testes passam**
em Python 3.14.4. Esse é o número anti-regressão — nenhuma tarefa pode reduzi-lo.

---

## Test Coverage Matrix

> Gerada do codebase e da spec. **Guidelines encontradas:** nenhuma (`AGENTS.md`,
> `CONTRIBUTING.md`, config de ruff/flake8/black/mypy e threshold de coverage: todos ausentes;
> `pyproject.toml` só define `testpaths=["tests"]`). Defaults fortes aplicados.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Cliente HTTP do router (`lifecycle/router.py`) | unit | Todos os ramos; 1:1 com ACs da spec; todo edge case listado (401, 404-arquivo, timeout, rede) | `tests/test_*.py` | `.venv/bin/python -m pytest -q` |
| Lógica de decisão (`lifecycle/params.py`, `lifecycle/manager.py`) | unit | Todos os ramos; 1:1 com ACs; toda a precedência e todo estado de plano | `tests/test_*.py` | `.venv/bin/python -m pytest -q` |
| Integração (provider, CLI, doctor, runner) | unit | Caminho feliz + todo caminho de erro que a tarefa introduz | `tests/test_*.py` | `.venv/bin/python -m pytest -q` |
| Dataclasses puras (`lifecycle/models.py`) | unit | Parsing e tolerância a chaves desconhecidas (têm comportamento, não são só schema) | `tests/test_*.py` | `.venv/bin/python -m pytest -q` |
| Validação ao vivo (`tests/test_live_router.py`) | integration | Opt-in por variável de ambiente; **nunca roda no CI** | `tests/test_live_*.py` | `HOMEBENCH_LIVE=1 .venv/bin/python -m pytest -q tests/test_live_router.py` |

**Nota de convenção:** o repo usa arquivos de teste planos em `tests/`, sem divisão
unit/e2e. Não existe suíte e2e separada — por isso `quick` e `full` são o mesmo comando.

## Gate Check Commands

> Extraídos do repo (`.github/workflows/ci.yml:27,38-39`, `pyproject.toml`). Não há linter
> nem formatter configurado neste projeto — o gate Build espelha o CI.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | Depois de qualquer tarefa com testes unitários | `.venv/bin/python -m pytest -q` |
| Full | Idem Quick (não há suíte e2e separada neste repo) | `.venv/bin/python -m pytest -q` |
| Build | Ao fechar uma fase | `.venv/bin/python -m pytest -q && .venv/bin/python -m build` |

---

## Execution Plan

### Phase 1: Cliente do router

```
T1 → T2
T1 → T3
T1 → T4
T3 → T5
```

### Phase 2: Resolução de parâmetros

```
T1 → T6
T6 → T8
T7 → T8
```

### Phase 3: Orquestração

```
T3 → T9
T8 → T9
T9 → T10
T10 → T11
```

### Phase 4: Integração no homebench

```
T2 → T12
T4 → T12
T8 → T13
T10 → T14
T12 → T14
T3 → T15
T12 → T15
T2 → T16
T12 → T16
```

### Phase 5: Validação ao vivo

```
T14 → T17
T15 → T17
```

---

## Task Breakdown

### T1: Dataclasses do ciclo de vida

**What**: Definir `RouterInfo`, `ModelState`, `LoadParams`, `LifecyclePlan`, `LifecycleOutcome` com parsing tolerante a chaves desconhecidas.
**Where**: `src/homebench/lifecycle/models.py`
**Depends on**: None
**Reuses**: padrão `_pick()` de `src/homebench/models.py:14-17`
**Requirement**: MLC-01

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] As cinco dataclasses existem com os campos do design
- [x] `ModelState.from_dict` aceita o payload real de `GET /v1/models` e ignora chaves desconhecidas
- [x] `status` fora de `{loaded, loading, unloaded}` é normalizado para `unloaded`
- [x] Testes em `tests/test_lifecycle_models.py`
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 6 testes passam (sem deleções silenciosas) — 174 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): add model lifecycle dataclasses`

---

### T2: `LlamaRouterClient.props()` e `is_router()`

**What**: Cliente base + detecção positiva de router via `GET /props`.
**Where**: `src/homebench/lifecycle/router.py`
**Depends on**: T1
**Reuses**: `normalize_host()` (`providers/openai_compat.py:26`), resolução de `api_key` (`openai_compat.py:44-48`), `ProviderError` (`providers/base.py:17`)
**Requirement**: MLC-07, MLC-10

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `props()` devolve `RouterInfo` a partir de `GET /props`
- [x] `is_router()` é `True` só quando `role == "router"`; 404, ausência do campo, JSON inválido e erro de rede ⇒ `False`
- [x] 401 levanta `ProviderError` dizendo que a autenticação foi recusada, **sem** ecoar a chave
- [x] Router inalcançável levanta `ProviderError` citando o host
- [x] Testes com `pytest_httpx` cobrindo: router ok, 401, 404, JSON inválido, rede caída
- [x] Nenhum teste faz requisição real
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 12 testes passam — 190 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): add router client with capability detection`

---

### T3: `list_models()` e `loaded_models()`

**What**: Ler estado e argv resolvido de todos os modelos.
**Where**: `src/homebench/lifecycle/router.py` (modificar)
**Depends on**: T1
**Reuses**: `ModelState.from_dict` (T1)
**Requirement**: MLC-01

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `list_models()` devolve `List[ModelState]` com `status`, `args`, `preset`, `source`
- [x] `args` é preenchido também para modelos `unloaded` (o router expõe o preset a frio)
- [x] `loaded_models()` filtra `status == "loaded"`
- [x] 401 e falha de rede levantam `ProviderError`
- [~] Fixture do teste usa o payload real capturado do router (17 modelos) — design.md não traz o payload capturado; fixture de 17 modelos reconstruída fielmente do contrato AD-001
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 18 testes passam — 196 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): list router models with resolved args`

---

### T4: `load()` e `unload()`

**What**: Os dois POSTs de mutação, com interpretação correta do 404.
**Where**: `src/homebench/lifecycle/router.py` (modificar)
**Depends on**: T1
**Reuses**: tratamento best-effort de `providers/ollama.py:149`
**Requirement**: MLC-02, MLC-06, MLC-13

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `load(model, extra_args=None)` envia `POST /models/load` com `{"model": id}` e inclui `extra_args` só quando não vazio
- [x] `unload(model)` envia `POST /models/unload` com `{"model": id}`
- [x] `404 File Not Found` vira `ProviderError` de **arquivo de modelo ausente**, citando o id — nunca "rota inexistente"
- [x] Erro do router é propagado com a mensagem original, sem reinterpretação
- [x] Testes cobrem: sucesso, 404-arquivo, 400-modelo-inexistente, `extra_args` presente e ausente
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 26 testes passam — 205 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): add model load and unload calls`

---

### T5: `wait_until_loaded()`

**What**: Aguardar a transição `loading → loaded` com timeout.
**Where**: `src/homebench/lifecycle/router.py` (modificar)
**Depends on**: T3
**Reuses**: `list_models()` (T3)
**Requirement**: MLC-05

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Retorna assim que o modelo fica `loaded`
- [x] Levanta `ProviderError` de timeout após `timeout` segundos (default 300, TD-06)
- [x] O relógio é injetável para que o teste de timeout não durma de verdade
- [x] Testes cobrem: já loaded, loading→loaded, timeout, modelo some da lista
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 32 testes passam — 211 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): wait for model load with timeout`

---

### T6: Override JSON de parâmetros

**What**: Ler o arquivo de override, degradando quando malformado.
**Where**: `src/homebench/lifecycle/params.py`
**Depends on**: T1
**Reuses**: `default_home()` (`history.py:31`)
**Requirement**: MLC-13

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `load_overrides(path=None)` lê `$HOMEBENCH_HOME/load-params.json` (TD-07)
- [x] Arquivo ausente devolve `{}` sem erro
- [x] JSON malformado devolve `{}` e sinaliza aviso — **não** levanta
- [~] Testes usam `tmp_path`; `conftest.py` já isola `HOMEBENCH_HOME` — não há `conftest.py` no repo; testes usam `monkeypatch.setenv("HOMEBENCH_HOME", ...)` como `test_history.py:106`
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 37 testes passam — 217 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): read load-param overrides from json`

---

### T7: Heurística de `-ngl`

**What**: Sugerir camadas em GPU a partir do tamanho do arquivo e do orçamento de memória.
**Where**: `src/homebench/lifecycle/params.py` (modificar)
**Depends on**: None
**Reuses**: `weight_bytes()`, `kv_cache_bytes()` (`catalog.py:112-127`), `memory_budget()` (`hardware.py:49-60`)
**Requirement**: MLC-13

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `suggest_ngl(file_bytes, budget_bytes)` devolve inteiro ≥ 0
- [x] Modelo que cabe folgado sugere offload total; modelo maior que o orçamento sugere 0
- [x] Orçamento zero ou negativo devolve 0 em vez de estourar
- [x] Testes constroem `HardwareInfo`/`GPUInfo` literais, como `tests/test_hardware_fit.py:35-55`
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 42 testes passam — 224 passam

**Nota:** a assinatura da tarefa (`suggest_ngl(file_bytes, budget_bytes)`) já recebe bytes prontos,
então `weight_bytes()`/`kv_cache_bytes()` (que convertem params_b→bytes) não se aplicam; o reuso
efetivo é `HardwareInfo.memory_budget()` nos testes.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): add ngl offload heuristic`

---

### T8: Precedência de resolução de parâmetros

**What**: Combinar as cinco fontes na ordem declarada e registrar a origem.
**Where**: `src/homebench/lifecycle/params.py` (modificar)
**Depends on**: T6, T7
**Reuses**: `load_overrides` (T6), `suggest_ngl` (T7)
**Requirement**: MLC-09, MLC-13

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `resolve()` aplica flag explícita > override JSON > preset do servidor > heurística > default
- [x] `LoadParams.origin` registra qual fonte venceu
- [x] Cada um dos cinco níveis tem teste isolado que prova que ele vence o nível abaixo
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 50 testes passam — 232 passam

**Nota:** `resolve()` recebe um kwarg extra `file_bytes: int = 0` (não previsto no sketch do
design) porque a heurística de `-ngl` precisa do tamanho do arquivo. Sem `hardware` **e**
`file_bytes`, a heurística é pulada e cai no default.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): resolve load params by precedence`

---

### T9: `plan()` — decidir sem agir

**What**: Produzir o `LifecyclePlan` a partir do estado do router, sem efeito colateral.
**Where**: `src/homebench/lifecycle/manager.py`
**Depends on**: T3, T8
**Reuses**: `LifecyclePlan` (T1), `list_models()` (T3)
**Requirement**: MLC-01, MLC-03, MLC-04

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `plan()` não faz nenhuma chamada de mutação (provado por teste com cliente falso que falha em `load`/`unload`)
- [x] Outros modelos residentes entram em `to_unload` — **todos**, não só o excedente (MLC-03)
- [~] Alvo já `loaded` com os mesmos parâmetros ⇒ `needs_load = False` e `to_unload` vazio (MLC-04) — `to_unload` fica vazio quando o alvo é o único residente; havendo outro residente ele continua em `to_unload`, porque a AC3 da spec (MLC-03) manda descarregar **todos** os outros. A AC4 proíbe descarregar/recarregar o **alvo**, e isso é o que o código faz
- [x] Alvo inexistente levanta `ProviderError` citando o id, sem plano (MLC-02)
- [x] `reason` é uma frase legível explicando o plano
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 59 testes passam — 242 passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): plan model state transitions without side effects`

---

### T10: `ensure_only()` com confirmação injetada

**What**: Executar o plano, pedindo confirmação antes de descarregar.
**Where**: `src/homebench/lifecycle/manager.py` (modificar)
**Depends on**: T9
**Reuses**: `plan()` (T9), `load`/`unload`/`wait_until_loaded` (T4, T5)
**Requirement**: MLC-06, MLC-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `ensure_only(model, params, confirm)` recebe `confirm` como callable e **nunca** chama `input()`
- [x] `confirm` retornando `False` aborta sem descarregar nada e sem carregar (MLC-08)
- [x] Plano com `to_unload` vazio não chama `confirm`
- [x] Falha de carga propaga `ProviderError` e não deixa carga parcial atribuída ao módulo (MLC-06)
- [x] Devolve `LifecycleOutcome` com os `args` efetivos pós-carga
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 68 testes passam — 252 passam

**Nota:** `LifecycleOutcome` ganhou o campo `aborted: bool = False` (não previsto no design).
É como a recusa da confirmação chega ao chamador sem virar exceção: `aborted=True`, nada
descarregado, nada carregado. `from_dict` continua tolerante a runs antigos.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(lifecycle): execute lifecycle plan with injected confirmation`

---

### T11: Teste de isolamento do pacote

**What**: Provar que `lifecycle/` não depende de TUI, provider nem runner (AD-005).
**Where**: `tests/test_lifecycle_isolation.py`
**Depends on**: T10
**Reuses**: —
**Requirement**: MLC-01

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Teste varre o AST de todo módulo em `src/homebench/lifecycle/` e falha se importar `tui`, `rich`, `textual`, `runner` ou `providers`
- [x] Exceção permitida e explícita: `providers.base.ProviderError` (tipo de erro compartilhado do repo)
- [x] O teste falha de fato se um import proibido for introduzido (verificado na hora: `import rich` + `from ..runner import RunConfig` em `manager.py` ⇒ `test_lifecycle_module_imports_nothing_forbidden[manager.py]` falhou; revertido)
- [x] Gate: `.venv/bin/python -m pytest -q && .venv/bin/python -m build`
- [x] Total ≥ 162 + 70 testes passam — 272 passam

**Nota:** o whitelist é o nó `ImportFrom` exato `from ..providers.base import ProviderError`
(a forma absoluta também). Alargar para `from ..providers.base import Provider, ProviderError`
é reprovado, e há teste para isso. Importar `homebench.lifecycle.router` puxa
`providers/__init__.py` em tempo de execução por causa desse nó — é o único acoplamento aceito.

**Tests**: unit
**Gate**: build
**Commit**: `test(lifecycle): enforce headless package boundary`

---

### T12: Provider llamacpp com detecção e `unload()` real

**What**: Ligar o ciclo de vida ao provider quando o host for router.
**Where**: `src/homebench/providers/llamacpp.py`
**Depends on**: T2, T4
**Reuses**: `LlamaRouterClient` (T2, T4); substitui o no-op herdado de `providers/base.py:74`
**Requirement**: MLC-14

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `unload()` envia `POST /models/unload` quando o host é router
- [x] Falha de unload é registrada e **não** interrompe o run (best-effort, MLC-14)
- [x] Host que não é router mantém `unload()` como no-op — sem exceção
- [x] Detecção é por instância/host, nunca cache global (AD-004)
- [x] Providers não-llamacpp seguem inalterados (teste de regressão)
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 78 testes passam — 285 passam

**Nota:** "registrar a falha" virou `provider.last_unload_error` (string inspecionável), não
`logging` nem `warnings.warn`: o repo não configura logging, e escrever em stderr durante o
run corromperia a TUI de tela cheia.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(providers): implement real unload for llamacpp router`

---

### T13: Persistir parâmetros de carga no resultado

**What**: Levar os parâmetros efetivos até o run salvo, furando a allowlist manual.
**Where**: `src/homebench/runner.py`
**Depends on**: T8
**Reuses**: `RunConfig.to_dict()` (`runner.py:72-87`), `history.save_run` persiste o resto de graça
**Requirement**: MLC-09

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Campo de parâmetros de carga existe em `RunConfig` **e** aparece em `to_dict()`
- [x] Teste anti-drift compara os campos do dataclass com as chaves de `to_dict()` e falha se divergirem (mitiga o risco registrado no design) — verificado na hora: um campo novo sem entrada em `to_dict()` faz `test_to_dict_serialises_every_runconfig_field` falhar
- [x] Dois runs do mesmo modelo com `-ngl` diferente são distinguíveis no JSON salvo
- [x] Runs antigos sem o campo seguem carregando (`_pick` já garante)
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 84 testes passam — 293 passam

**Nota:** o teste anti-drift precisa de uma lista explícita de exclusões (`NOT_SERIALISED`),
porque `to_dict()` já omitia `suite`, `speed_prompt`, `timeout`, `use_cache` e `refresh_cache`
antes desta feature. As três últimas são dívida pré-existente, **não corrigida aqui** (fora de
escopo); ficam registradas na lista para que a omissão seja deliberada e visível.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(runner): record effective load params in run results`

---

### T14: Fluxo de confirmação na CLI

**What**: Ligar o manager ao `cmd_run`, com `--force-unload`.
**Where**: `src/homebench/cli.py`
**Depends on**: T10, T12
**Reuses**: `ensure_only` (T10), padrão `cmd_*(args, console) -> int` (`cli.py:316`)
**Requirement**: MLC-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] `--force-unload` existe e pula a confirmação
- [x] Sem a flag, a confirmação lista **quais** modelos serão descarregados antes de perguntar
- [x] Entrada não interativa sem a flag aborta com mensagem dizendo como prosseguir — nunca descarrega sozinho (MLC-08)
- [x] Recusa aborta sem descarregar e sem rodar benchmark
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 91 testes passam — 309 passam

**Notas:**
1. `_prepare_router_models` prepara **o primeiro** modelo selecionado, uma vez, antes do run.
   Chamar `ensure_only` por modelo dentro do laço exigiria mexer em `runner.py:_run_model`, que
   não está no escopo de nenhuma tarefa desta feature. Para N modelos, os demais dependem de
   `unload_between` (T12) + `warmup`. Lacuna conhecida, registrada aqui.
2. A CLI **não** reenvia como `extra_args` os parâmetros de origem `preset`/`default`: `resolve()`
   devolve em `extra_args` o argv inteiro que o servidor já resolveu, e mandá-lo de volta
   duplicaria a linha de comando do router. Só `explicit`, `json` e `heuristic` são enviados.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): add guarded unload confirmation flow`

---

### T15: Subcomando de inspeção de modelos

**What**: Comando que lista modelos, estado e parâmetros efetivos.
**Where**: `src/homebench/cli.py` (modificar)
**Depends on**: T3, T12
**Reuses**: `list_models()` (T3), tabelas Rich de `report.py`
**Requirement**: MLC-10

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Subcomando lista cada modelo com estado; residentes mostram os parâmetros efetivos
- [x] O nome está em `_COMMANDS` (`cli.py:182`)
- [x] **Teste paramétrico** cobre todos os subparsers registrados vs `_COMMANDS`, falhando se divergirem (mitiga o risco registrado no design) — verificado na hora: tirar `"models"` de `_COMMANDS` quebra 11 testes
- [x] Router inalcançável reporta erro citando o host, sem stack trace
- [x] Gate: `.venv/bin/python -m pytest -q`
- [x] Total ≥ 162 + 98 testes passam — 338 passam

**Nota:** `cmd_models` fala direto com `LlamaRouterClient`, sem passar por `_resolve_provider`.
É o que permite citar o host na falha: o erro de `_resolve_provider` diz só "provider não
alcançável", enquanto `ProviderError` do cliente já traz o host. `--provider` diferente de
`llamacpp` é recusado com explicação.

**Tests**: unit
**Gate**: quick
**Commit**: `feat(cli): add models inspection subcommand`

---

### T16: Checagens de router no `doctor`

**What**: Diagnóstico de alcançabilidade e autenticação do router.
**Where**: `src/homebench/doctor.py`
**Depends on**: T2, T12
**Reuses**: dataclass `Check` e `run_checks()` (`doctor.py:17,42`)
**Requirement**: MLC-12

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] Host router alcançável e autenticado ⇒ `ok`, citando `build_info` e quantos modelos estão residentes
- [x] 401 ⇒ `fail` dizendo que a chave foi recusada, **sem** exibir a chave
- [x] Inalcançável ⇒ `fail` citando o host, sem stack trace (MLC-12)
- [x] `doctor` segue funcionando sem nenhum router presente
- [x] Gate: `.venv/bin/python -m pytest -q && .venv/bin/python -m build`
- [x] Total ≥ 162 + 104 testes passam — 349 passam

**Nota:** a checagem só roda quando há host llama.cpp em jogo (`_router_expected`: `LLAMACPP_HOST`
definido **ou** llamacpp detectado alcançável). Sem esse portão, quem roda só Ollama ganharia um
`fail` novo em `doctor` — e `fail` faz o comando sair com código 1. Host llama.cpp clássico
(não-router) vira `info`, não `fail`: é um setup saudável.

**Tests**: unit
**Gate**: build
**Commit**: `feat(doctor): add router reachability and auth checks`

---

### T17: Teste ao vivo opt-in contra os dois hosts

**What**: Teste de integração real, desligado por padrão, contra vulkan e rocm.
**Where**: `tests/test_live_router.py`
**Depends on**: T14, T15
**Reuses**: `LlamaRouterClient`, `ensure_only`
**Requirement**: MLC-15

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [x] O módulo inteiro é pulado sem `HOMEBENCH_LIVE=1` — `pytest -q` normal segue em 162 + novos, e o **CI não o executa** (`.github/workflows/ci.yml` roda `pytest -q` puro, sem env)
- [x] Ciclo completo contra `:8080` e `:8081`: estado inicial → load → `loaded` → geração curta → unload → estado original restaurado
- [x] Usa o menor modelo disponível, não um fixo hardcoded (`-m <path>` do argv resolvido + `os.path.getsize`)
- [x] Registra `build_info` de cada host e **falha com aviso claro se os builds divergirem** (hoje `b10615` vs `b10664`), porque isso invalida a comparação Vulkan vs ROCm
- [x] O teste restaura o estado inicial mesmo em caso de falha (`try/finally`)
- [x] Gate: `.venv/bin/python -m pytest -q && .venv/bin/python -m build`
- [x] Total ≥ 162 + 104 testes passam sem a env var — 349 passam, 5 pulados

**Nota:** escrito e verificado como pulado, mas **não executado ao vivo** nesta sessão, por
instrução explícita: os containers servem Open WebUI + Traefik em produção e descarregar um
modelo poderia derrubar a sessão de alguém. A execução ao vivo exige confirmação do usuário.
Coletado com `HOMEBENCH_LIVE=1 pytest --collect-only` (5 testes, sem rede) para provar que o
caminho ao vivo importa e parametriza corretamente.

**Tests**: integration
**Gate**: build
**Commit**: `test(lifecycle): add opt-in live router integration test`

---

## Phase Execution Map

Fases rodam em sequência (1 → 2 → 3 → 4 → 5); dentro da fase, as tarefas rodam em ordem.
Lista completa de arestas de dependência:

```
T1 → T2
T1 → T3
T1 → T4
T3 → T5
T1 → T6
T6 → T8
T7 → T8
T3 → T9
T8 → T9
T9 → T10
T10 → T11
T2 → T12
T4 → T12
T8 → T13
T10 → T14
T12 → T14
T3 → T15
T12 → T15
T2 → T16
T12 → T16
T14 → T17
T15 → T17
```

`T1` e `T7` não têm dependência de entrada. Nenhuma aresta aponta para fase posterior.

**Empacotamento em batches** (~7 tarefas por worker, fases inteiras, cortes só em fronteira):

| Batch | Fases | Tarefas | Tier | Por quê |
| --- | --- | --- | --- | --- |
| 1 | Phase 1 + Phase 2 | 8 (T1–T8) | **Sonnet** (mais barato) | Trabalho mecânico contra contrato já verificado: dataclasses, cliente HTTP com `openai_compat.py` de molde, casos de erro já enumerados na tabela do design. Baixa ambiguidade |
| 2 | Phase 3 + Phase 4 + Phase 5 | 9 (T9–T17) | **Opus** (alto raciocínio) | Domínio de verdade + integração com armadilhas conhecidas: allowlist manual do `to_dict`, acoplamento do `_COMMANDS`, e teste ao vivo contra serviço de produção com restauração de estado |
| — | Verifier | — | **Opus** | A rubrica proíbe o tier mais barato aqui: ele projeta mutações adversariais. Verifier fraco anula o portão `author ≠ verifier` |

Phase 5 é cauda solta de 1 tarefa e foi dobrada no batch 2, conforme o algoritmo.

**Total: 2 batch workers + 1 Verifier = 3 subagentes**, sequenciais — nunca mais de um vivo.
Cumpre exatamente o limite pedido pelo usuário.

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1 | 1 arquivo, dataclasses coesas | ✅ Granular |
| T2 | 2 métodos coesos, 1 arquivo | ✅ Granular |
| T3 | 2 métodos coesos, 1 arquivo | ✅ Granular |
| T4 | 2 métodos simétricos, 1 arquivo | ✅ Granular |
| T5 | 1 método | ✅ Granular |
| T6 | 1 função | ✅ Granular |
| T7 | 1 função | ✅ Granular |
| T8 | 1 função | ✅ Granular |
| T9 | 1 método | ✅ Granular |
| T10 | 1 método | ✅ Granular |
| T11 | 1 arquivo de teste | ✅ Granular |
| T12 | 1 arquivo, 1 comportamento | ✅ Granular |
| T13 | 1 arquivo, 1 campo + guarda | ✅ Granular |
| T14 | 1 arquivo, 1 fluxo | ✅ Granular |
| T15 | 1 arquivo, 1 subcomando | ✅ Granular |
| T16 | 1 arquivo, 1 grupo de checagens | ✅ Granular |
| T17 | 1 arquivo de teste | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (corpo) | Diagrama mostra | Status |
| --- | --- | --- | --- |
| T1 | None | sem seta de entrada | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T1 | T1 → T3 | ✅ Match |
| T4 | T1 | T1 → T4 | ✅ Match |
| T5 | T3 | T3 → T5 | ✅ Match |
| T6 | T1 | T1 → T6 | ✅ Match |
| T7 | None | sem seta de entrada | ✅ Match |
| T8 | T6, T7 | T6 → T8, T7 → T8 | ✅ Match |
| T9 | T3, T8 | T3 → T9, T8 → T9 | ✅ Match |
| T10 | T9 | T9 → T10 | ✅ Match |
| T11 | T10 | T10 → T11 | ✅ Match |
| T12 | T2, T4 | T2 → T12, T4 → T12 | ✅ Match |
| T13 | T8 | T8 → T13 | ✅ Match |
| T14 | T10, T12 | T10 → T14, T12 → T14 | ✅ Match |
| T15 | T3, T12 | T3 → T15, T12 → T15 | ✅ Match |
| T16 | T2, T12 | T2 → T16, T12 → T16 | ✅ Match |
| T17 | T14, T15 | T14 → T17, T15 → T17 | ✅ Match |

Nenhuma dependência aponta para fase posterior. Arestas entre fases aparecem no diagrama da
fase de destino, e todas constam do mapa de execução completo.

---

## Test Co-location Validation

| Task | Camada criada/modificada | Matriz exige | Tarefa diz | Status |
| --- | --- | --- | --- | --- |
| T1 | Dataclasses com parsing | unit | unit | ✅ OK |
| T2 | Cliente HTTP do router | unit | unit | ✅ OK |
| T3 | Cliente HTTP do router | unit | unit | ✅ OK |
| T4 | Cliente HTTP do router | unit | unit | ✅ OK |
| T5 | Cliente HTTP do router | unit | unit | ✅ OK |
| T6 | Lógica de decisão | unit | unit | ✅ OK |
| T7 | Lógica de decisão | unit | unit | ✅ OK |
| T8 | Lógica de decisão | unit | unit | ✅ OK |
| T9 | Lógica de decisão | unit | unit | ✅ OK |
| T10 | Lógica de decisão | unit | unit | ✅ OK |
| T11 | Teste de fronteira | unit | unit | ✅ OK |
| T12 | Integração (provider) | unit | unit | ✅ OK |
| T13 | Integração (runner) | unit | unit | ✅ OK |
| T14 | Integração (CLI) | unit | unit | ✅ OK |
| T15 | Integração (CLI) | unit | unit | ✅ OK |
| T16 | Integração (doctor) | unit | unit | ✅ OK |
| T17 | Validação ao vivo | integration | integration | ✅ OK |

Nenhum `Tests: none`. Nenhuma violação.

---

## Fix Tasks — iteração 1 (pós-verificação)

O Verifier independente reprovou a entrega (`validation.md`, veredito FAIL: M16 sobreviveu, 4
edge cases sem evidência). O usuário escolheu corrigir o bloqueador + as duas lacunas de teste e
adiar o resto (AD-006).

### F1 — `ensure_only` roda por modelo, não só no primeiro ✅

**What**: hook `prepare_model` no `Runner`, chamado no início do turno de cada modelo; a garantia
"só o alvo residente" (MLC-01/MLC-03) e o registro de `load_params` (MLC-09) passam a valer para
todos os modelos de um run com vários.
**Where**: `src/homebench/runner.py`, `src/homebench/cli.py`, `src/homebench/plainui.py`
**Requirement**: MLC-01, MLC-03, MLC-09
**Done when**:
- [x] `Runner(prepare_model=...)`; chamado 1×/modelo antes do warmup, emite `phase="prepare"`
- [x] `_prepare_router_models` devolve `(proceed, prepare_hook)`; confirma só os residentes que
      o run **não** vai medir (AD-002), depois cicla os modelos do run livremente
- [x] `load_params` no resultado salvo tem uma entrada por modelo, não só a do primeiro
- [x] Mutação M16 (`models[0]` → `models[-1]`) fica sem alvo — o loop cobre todos
- [x] `tests/test_runner_prepare_hook.py` (8) + `tests/test_cli_lifecycle.py` reescrito
- [x] Gate: `.venv/bin/python -m pytest -q` — 366 passam
**Commit**: `fix(runner): prepare each measured model, not just the first`

### F4 — teste de isolamento de falha no meio do run ✅

**What**: prova que um `ProviderError` no meio do run (router reiniciando) falha só o modelo
corrente; os demais seguem.
**Where**: `tests/test_runner_error_isolation.py`, `tests/test_lifecycle_manager.py`
**Requirement**: MLC-11, MLC-06
**Done when**:
- [x] Provider que levanta `ProviderError` para 1 de 3 modelos ⇒ `reports[i].error` setado, os
      outros dois medem normalmente, run completa
- [x] `load()` POST que falha não deixa nada carregado e não dispara unload espúrio
- [x] Gate: 370 passam
**Commit**: `test(runner): cover mid-run ProviderError isolation (MLC-11)`

### F6 — falha de unload chega ao relatório ✅

**What**: `ModelReport.warnings` recebe a falha de unload best-effort; mostrada depois do
leaderboard e emitida como `phase="warning"`.
**Where**: `src/homebench/models.py`, `src/homebench/runner.py`, `src/homebench/plainui.py`
**Requirement**: MLC-14
**Done when**:
- [x] `ModelReport.warnings: List[str]`, em `to_dict`/`from_dict`, tolerante a runs antigos
- [x] `tests/test_runner_unload_warning.py` (7)
- [x] Gate: 356 passam
**Commit**: `fix(runner): surface best-effort unload failures on the model report`

### Adiado (AD-006) — não implementado nesta feature

MLC-15 (comparar backends), aviso de requisição em voo, retry de `--models-max`, heurística de
`-ngl` no caminho de produção, teste de não-dedup cross-backend. Motivos em STATE.md § AD-006.
