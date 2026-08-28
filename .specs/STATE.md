# Project State

Memória de projeto: log de decisões + snapshot de handoff.

## Decisions

### AD-001 — Ciclo de vida do modelo via API do router, não via processo/container

**Data:** 2026-08-28 · **Status:** Aceita

**Contexto.** O documento de produto (`contexto-llm-benchmark.md`) parte da premissa de que a
ferramenta precisa subir o processo `llama-server` com flags (`-ngl`, `-c`, `-fa`), porque o
homebench upstream não gerencia ciclo de vida de modelo.

**Descoberta.** A premissa não se aplica a este ambiente. O `llama.cpp` roda em **modo router**
(`GET /props` → `"role":"router"`, `max_instances: 2`, `models_autoload: false`, build
`b10615-f280b2698`), em dois containers Docker — `llama-vulkan` (`127.0.0.1:8080`) e `llama-rocm`
(`127.0.0.1:8081`) — ambos `restart: always`, fronteados por Traefik e consumidos pelo Open WebUI.
O router já é dono do ciclo de vida, por HTTP.

**Contrato verificado ao vivo** (teste de fumaça autorizado, `qwen35-4b`, 28/08/2026):

```
POST /models/load    {"model": id, "extra_args": [...]}  → {"success": true}   (loaded em 4s)
POST /models/unload  {"model": id}                       → {"success": true}
GET  /v1/models      → data[].status.value ∈ {loaded, loading, unloaded}
                       data[].status.args  → argv já resolvido pelo servidor
GET  /models/sse     → stream de eventos de status
```

**Decisão.** O módulo de ciclo de vida é um **cliente HTTP** do router. A ferramenta nunca
inicia, para ou reinicia processo ou container.

**Consequências.**
- Sem `subprocess`, `docker exec`, sudo ou systemd; fica na convenção `httpx` do repo.
- Testável com `pytest-httpx`, como os providers existentes.
- Já compatível com a futura API web (HTTP puro, sem acesso ao host).
- Mexer nos containers seria destrutivo para serviço de produção (Open WebUI, Traefik).
- `extra_args` cobre nativamente "parâmetros editáveis antes de carregar" (item 4 do fluxo).
- `/models/sse` cobre o progresso ao vivo (item 6) sem polling.

**Correção de registro.** Uma sondagem inicial com nome de modelo falso retornou `404 File Not
Found` em `POST /models/load`, e isso foi lido como "rota ausente neste build". Estava errado: a
rota existe; o 404 se referia ao *arquivo do modelo*. Confirmado pelo bundle do painel web e pelo
teste de fumaça.

---

### AD-002 — Descarregar exige confirmação

**Data:** 2026-08-28 · **Status:** Aceita

Os containers do router servem produção. Descarregar um modelo residente é uma ação destrutiva
para terceiros. Padrão: mostrar o que será descarregado e pedir confirmação; `--force-unload`
pula para uso não interativo. Escolhido pelo usuário.

---

### AD-003 — Parâmetros de carga por precedência híbrida

**Data:** 2026-08-28 · **Status:** Aceita

Precedência: flag explícita > override JSON > preset já resolvido pelo servidor > heurística >
default do llama.cpp. O preset resolvido vem de graça em `status.args`, então a heurística só
cobre modelos sem preset. Escolhido pelo usuário.

---

### AD-004 — Capacidade de router detectada por host, via `GET /props`

**Data:** 2026-08-28 · **Status:** Aceita

`--provider llamacpp` continua sendo o nome usado. A ferramenta pergunta ao servidor
(`GET /props`) e liga o gerenciamento de modelo quando `role == "router"`. Escolhido pelo usuário.

O teste é **positivo** (`role == "router"`); ausência do campo, 404 ou erro de parse ⇒ não é
router. Motivo: não temos um `llama-server` clássico para observar o formato do não-router, e um
teste positivo é seguro sem esse conhecimento.

**Detecção é por host, nunca cache global.** Os dois hosts do ambiente rodam builds diferentes —
vulkan `b10615-f280b2698`, rocm `b10664-e70802a01`. Isso também significa que comparar Vulkan vs
ROCm mistura backend com versão enquanto os builds divergirem; `build_info` deve ser gravado por
host no resultado.

---

### AD-005 — `lifecycle/` é headless

**Data:** 2026-08-28 · **Status:** Aceita

O pacote `lifecycle/` não importa `providers/`, `tui/`, `runner.py` nem `rich`. A dependência é
unidirecional: o provider e a CLI usam o módulo, nunca o contrário. Interação com o usuário entra
por um `Confirmer` injetado (callable), não por `input()` embutido.

Cumpre a restrição do doc de contexto de que a lógica de negócio sirva à TUI e à futura API web.
Verificável por teste de import — vale para as features seguintes (painel GPU, perfis, fluxo guiado).

---

## Handoff

**Onde parou:** Specify, Design e Tasks **concluídos e aprovados pelo usuário** em 2026-08-28.
Ambos os gates determinísticos passaram: `validate_spec.py` → 0 erros ·
`validate_tasks.py` → 0 erros. **Próxima fase: Execute (T1).**

**Nada implementado ainda.** Nenhum arquivo em `src/` foi tocado. `git status` limpo exceto
os artefatos de planejamento não commitados.

### Precondição de ambiente (satisfeita)

`.venv/` criado e `pip install -e ".[dev]"` feito. **162 testes passam** em Python 3.14.4
(`.venv/bin/python -m pytest -q`). Esse é o número anti-regressão. `.venv/` está no `.gitignore`.
Atenção: o Python local é 3.14, mais novo que a matriz do CI (3.9–3.12).

### Plano de execução aprovado

| Batch | Fases | Tarefas | Modelo |
| --- | --- | --- | --- |
| 1 | Phase 1 + 2 | T1–T8 (8) | **Sonnet** — mecânico, contrato já verificado |
| 2 | Phase 3 + 4 + 5 | T9–T17 (9) | **Opus** — domínio + integração com armadilhas |
| Verifier | — | — | **Opus** — nunca o tier mais barato |

Sequenciais: nunca mais de um subagente vivo. Total 3, conforme limite pedido pelo usuário.

**Suposições da spec, decididas no design:** timeout de carga = 300 s (TD-06) ·
override JSON em `$HOMEBENCH_HOME/load-params.json` (TD-07) · `extra_args` não validado no
cliente (TD-05).

### Autorizações e proibições permanentes

- **Autorizado:** teste de fumaça ao vivo contra `:8080` e `:8081`, com os modelos em
  `/home/ai-models`. A chave fica em `~/llm-server/llama/api-key.txt` — **nunca logar nem commitar**.
- **Proibido:** iniciar, parar ou reiniciar qualquer container. Servem Open WebUI e Traefik em
  produção (AD-001).
- **Proibido sem autorização explícita:** `git push` e qualquer operação remota. Aprovar tasks
  autoriza apenas implementação e commits **locais**.

**Dívidas pré-existentes encontradas durante o design** (não são desta feature, mas foram
registradas em `design.md § Risks & Concerns`): ordenação "3 menores" é no-op no llamacpp porque
`size_bytes` é sempre 0 (`cli.py:221`) · subcontagem de tokens com `reasoning_content`
(`openai_compat.py:130`, diferido como MLC-16) · `_measure_speed` não captura `ProviderError`
(`runner.py:187`).

**Nada implementado ainda.** Nenhum arquivo em `src/` foi tocado.

**Artefatos relacionados:**
- `docs/plano-modulo-ciclo-de-vida.md` — plano e achados de ambiente
- `contexto-llm-benchmark.md` — documento de produto original (premissa corrigida por AD-001)
- `CLAUDE.md` — seção "This fork's direction"

**Próximo passo:** Execute — despachar o Batch 1 (T1–T8) em Sonnet.
