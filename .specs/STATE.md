# Project State

Memória de projeto: log de decisões + snapshot de handoff.

## Decisions

### AD-001 — Ciclo de vida do modelo via API do router, não via processo/container

**Data:** 2026-08-28 · **Status:** Aceita

**Contexto.** O documento de produto (`docs/contexto-llm-benchmark.md`) parte da premissa de que a
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

### AD-006 — Itens adiados após a verificação da feature

**Data:** 2026-08-28 · **Status:** Aceita (escolhido pelo usuário)

O Verifier independente reprovou a primeira entrega (`validation.md`) e listou 7 correções. O
usuário optou por corrigir o bloqueador e as duas lacunas de teste, e **adiar formalmente** o
resto. Corrigido nesta iteração:

- **Fix 1 (bloqueador)** — a garantia "só o alvo está carregado" agora roda por modelo, dentro
  do `Runner`, via um `prepare_model` hook. Antes só valia para o primeiro modelo de um run
  com vários. `load_params` também passa a ser gravado por modelo.
- **Fix 4** — teste novo provando que um `ProviderError` no meio do run (router reiniciando)
  falha só o modelo corrente (MLC-11).
- **Fix 6** — falha de `unload` best-effort agora vai para `ModelReport.warnings` (persistida e
  mostrada depois do leaderboard) além de emitir evento `phase="warning"`.

Adiado, com motivo:

| Item | Requisito | Por que adiar |
| --- | --- | --- |
| Comparação Vulkan vs ROCm de dois hosts | MLC-15 (P3) | Nunca foi MVP. Os dois hosts rodam builds diferentes (`b10615` vs `b10664`), então a comparação mistura backend com versão e é inválida hoje. Reabrir quando os builds convergirem. |
| Aviso de "requisição em voo" antes de descarregar | Edge case / risco 2 do plano | O build `b10615` do router **não expõe** contagem de requisições ativas em nenhum endpoint verificado (`/props`, `/v1/models`, `/models/sse`). A confirmação obrigatória (AD-002) já cobre o risco de fundo. Reabrir se um build futuro adicionar `/slots` ao router. |
| `--models-max` atingido durante carga ⇒ liberar o mais antigo e repetir | Edge case | O `plan()` já descarrega **todos** os outros residentes antes de carregar (MLC-03), então o limite nunca é atingido no caminho da ferramenta. Moot por construção. |
| Heurística de `-ngl` no caminho de produção | MLC-13 P2 AC5 | O CLI (`_prepare_router_models`) nunca passa `hardware=`/`file_bytes=` para `resolve()`, então o nível heurístico nunca é alcançado — `suggest_ngl` fica testado mas sem chamador em `src/`. Ligar isso é uma adição de feature, não uma correção; adiado. |
| Mesmo modelo nos dois backends sem deduplicar | Edge case | N/A por construção: cada `LlamaRouterClient` fala com um host só e o run usa um provider por vez. E o edge case pede "ids diferentes" — não há o que deduplicar. |

O aviso de "requisição em voo" continua adiado (o router não publica requisições ativas), mas
a mitigação que o justificava mudou: ver AD-007.

---

### AD-007 — Escopo da confirmação de descarga após o hook por modelo

**Data:** 2026-08-28 · **Status:** Aceita (segue a intenção do Fix 1, aprovado pelo usuário)

O Fix 1 (garantia por modelo dentro do `Runner`) mudou, de fato, quando a confirmação da MLC-08
é pedida. A iteração 2 do Verifier apontou que isso estreitou uma AC P1 sem registro.

**Decisão.** A confirmação (`MLC-08 AC1`) cobre os modelos residentes que **o run não vai medir**
— tipicamente uma sessão de terceiro no Open WebUI. Escolher um modelo para o benchmark **é** a
autorização para descarregá-lo e recarregá-lo no turno dele; pedir confirmação a cada troca de
modelo num run de vários seria absurdo e o `--models-max 2` torna a troca rotina.

**Salvaguarda.** Se um modelo que **não** está na lista aprovada (nem é medido pelo run, nem
estava residente e aprovado no início) aparecer residente durante o run, o `prepare` daquele
modelo levanta `ProviderError` — falha só aquele modelo, com mensagem para re-rodar — em vez de
descarregar o intruso silenciosamente. (`cli.py::_prepare_router_models._authorise`,
`tests/test_cli_lifecycle.py::test_a_model_that_becomes_resident_mid_run_is_not_unloaded_silently`.)

**Consequência para AD-006.** O item "aviso de requisição em voo" segue adiado, mas sua
justificativa agora é a salvaguarda acima + a confirmação up-front, não uma confirmação por
descarga individual.

---

### AD-008 — Config persistida em `$HOMEBENCH_HOME/config.json`; env ganha; chave só como path

**Data:** 2026-09-10 · **Status:** Aceita

O caminho cotidiano deixa de ser export manual. `setup.sh` e o painel gravam `host`,
`api_key_file`, `model_dir` e `last_plan` em `$HOMEBENCH_HOME/config.json` (default
`~/.homebench/config.json`). Variáveis já definidas (`LLAMACPP_HOST`, `LLAMACPP_API_KEY`,
`HOMEBENCH_MODEL_DIR`) ganham do arquivo. O valor da chave **nunca** é escrito no JSON: só o
caminho do arquivo; a leitura é na hora, em memória.

**Trade-off.** Um arquivo a mais vs. só env. Sem o arquivo o operador volta ao `docs/USO.md`.

**Scope.** Qualquer entrada (`panel`, `run`, `doctor`, `models`) deve chamar `apply_to_environ`
cedo. Futura API web reusa o mesmo `config.py`.

---

### AD-009 — Argv vazio em TTY abre o painel, não o run

**Data:** 2026-09-10 · **Status:** Aceita

`homebench` sem argumentos, com stdin e stdout TTY, abre o painel BIOS. Sem TTY (pytest, pipe,
CI) o argv vazio continua sendo `run`, para não quebrar scripts. Qualquer argumento preserva a
CLI atual. Escolhido pelo operador (item 4 da discussão guided-ops).

**Trade-off.** Quem digitava `homebench` e esperava os 3 menores automaticamente agora cai no
painel. O atalho antigo é `homebench run`.

**Scope.** `_inject_default_command` e o subcomando `panel`. Features seguintes não devem
voltar a injetar `run` no TTY vazio.

---


## Handoff

- **Feature**: guided-ops (`.specs/features/guided-ops/`)
- **Phase / Task**: Execute completo. Hotfix teclado BIOS (GOPS-24–27) verificado.
- **Completed**: T1–T16; dotted-id `4ca26fc`; menu setas/Enter/Esc `2b5ddfe`.
- **In-progress**: none
- **Next step**: Operador testa `homebench`: setas no menu, Enter abre, Esc volta/sai. Sem `git push` sem autorização.
- **Blockers**: none
- **Uncommitted files**: `setup.sh` mode `100755` (fora deste hotfix)
- **Branch**: `feat/guided-ops` (1 commit local à frente de origin até o relatório de validação)

**Proibições permanentes:** sem Docker/sudo/container (AD-001); sem logar/commitar a API key; sem `git push` sem autorização na hora.

**Proibições permanentes:** sem Docker/sudo/container (AD-001); sem logar/commitar a API key; sem `git push` sem autorização na hora.

---
