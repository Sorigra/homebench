# Plano — Módulo de gerenciamento de ciclo de vida do modelo

Documento de planejamento. Nenhum código foi escrito ainda.
Contexto de origem: [`contexto-llm-benchmark.md`](../contexto-llm-benchmark.md).

---

## 1. Contexto

O fork do `homebench` vai virar uma ferramenta de teste de **performance bruta** de LLMs locais,
rodando num mini PC AMD (Strix Halo). O documento de contexto identificou como peça central
faltante o **gerenciamento do ciclo de vida do modelo**: detectar o que está carregado,
descarregar, e subir o modelo com os parâmetros certos.

### A descoberta que muda a premissa

O documento de contexto assume que a ferramenta precisa **subir o processo `llama-server`** com
flags (`-ngl`, `-c`, `-fa`). **Isso não se aplica a este ambiente.** A inspeção do ambiente real
mostrou que o `llama.cpp` aqui roda em **modo router**, dentro de Docker, e o router **já é dono
do ciclo de vida do modelo, via HTTP**.

Evidências coletadas:

| Fato | Evidência |
| --- | --- |
| Dois backends em containers | `llama-vulkan` → `127.0.0.1:8080`, `llama-rocm` → `127.0.0.1:8081`, ambos `restart: always` |
| É um router, não um servidor de modelo único | `GET /props` → `{"role":"router","max_instances":2,"models_autoload":false,"build_info":"b10615-f280b2698"}` |
| O router lista estado por modelo | `GET /v1/models` → 17 modelos, cada um com `status.value` (`loaded`/`unloaded`) |
| O router expõe os parâmetros já resolvidos | Cada modelo traz o `argv` final (`--n-gpu-layers`, `--flash-attn`, `--ubatch-size`, `--ctx-size`, `--model`) e o texto do preset |
| Descarregar já existe como endpoint | `POST /models/unload {"model": id}` → `{"success":true}` |
| Carregar também existe | `POST /models/load {"model": id, "extra_args": [...]}` → `{"success":true}` |
| Stream de status ao vivo | `GET /models/sse` — eventos de mudança de estado, sem polling |
| Estados possíveis | `loaded` · `loading` · `unloaded` |
| Parâmetros recomendados já são versionados | `presets.ini` / `presets-rocm.ini`, com seção `[*]` de defaults |
| A API é autenticada | Bearer token, arquivo `llm-server/llama/api-key.txt` |

### Consequência: o módulo é um cliente HTTP, não um orquestrador de processos

Isso é uma simplificação grande, e em várias dimensões:

- **Sem `subprocess`, sem `docker exec`, sem `sudo`, sem systemd.** Fica dentro da convenção
  `httpx` que o homebench já usa em todos os providers.
- **Testável com `pytest-httpx`**, exatamente como os providers existentes — sem precisar mockar
  processo nem Docker.
- **Não briga com `restart: always`.** Derrubar container seria contraproducente: os mesmos
  containers servem o Open WebUI e têm rotas no Traefik (`llm-vulkan.dev.eskudo.io`,
  `llm-rocm.dev.eskudo.io`). Mexer no processo quebraria serviço de produção; a API do router não.
- **Já nasce compatível com a futura API web**, que era uma restrição arquitetural declarada:
  é HTTP puro, não exige acesso ao host.

### Um segundo ganho: benchmark de backend

Como há **dois backends sobre o mesmo hardware e os mesmos arquivos** (`/home/ai-models` montado
`:ro` nos dois), comparar **Vulkan vs ROCm no mesmo modelo** passa a ser um caso de uso de
primeira classe — algo que o homebench original não tinha como expressar. O módulo deve tratar
"qual host" como parâmetro normal, não como configuração global.

---

## 2. Escopo

**Dentro** (esta feature):

1. Detectar o que está carregado em um backend, com os parâmetros efetivos.
2. Descarregar, **pedindo confirmação por padrão** (flag para pular, para uso não interativo).
3. Carregar um modelo com parâmetros escolhidos.
4. Resolver parâmetros recomendados (**híbrido**: heurística + override JSON).
5. Integrar ao homebench: `unload()` real no provider, mais um subcomando de inspeção.

**Fora** (viram features seguintes, na mesma estrutura):
painel de GPU AMD ao vivo · perfis de teste · fluxo guiado na TUI · download de modelos.

### Decisões já tomadas

| Decisão | Escolha |
| --- | --- |
| Controle do processo | Via **API do router** (não subprocesso, não Docker) — revisão da decisão original, justificada acima |
| Parâmetros recomendados | **Híbrido**: heurística + override JSON |
| Modelo já carregado | **Pede confirmação**, com flag para pular |
| Teste de fumaça ao vivo | **Autorizado** pelo usuário, usando os modelos em `/home/ai-models` |

---

## 3. Arquitetura

Módulo novo `src/homebench/lifecycle/`, **headless** — sem importar nada de `tui/` ou `rich`,
conforme a decisão de manter lógica de negócio reutilizável pela futura API web.

```
lifecycle/
├── router.py     LlamaRouterClient — cliente HTTP do router
├── params.py     resolução de parâmetros (heurística + override JSON)
└── manager.py    ModelLifecycleManager — orquestração
```

- **`router.py`** — `list_models()`, `status(model)`, `load(model, params)`, `unload(model)`,
  e um `capabilities()` que **detecta em runtime** se `POST /models/load` existe. Segue o
  contrato do repo: erros viram `ProviderError`; operações best-effort não levantam exceção.
- **`params.py`** — precedência: **flag explícita > override JSON do usuário > preset já
  resolvido pelo servidor > heurística > default do llama.cpp**.
- **`manager.py`** — `ensure_only(model)`: consulta estado → decide o que descarregar →
  confirma → descarrega → carrega → espera ficar pronto.

### Aproveitamento do que já existe (não reinventar)

| Alvo | O que já existe | Ação |
| --- | --- | --- |
| `providers/llamacpp.py` | Subclasse de 5 linhas; `unload()` é **no-op herdado** (`base.py:74`) | Ganha `unload()` real e `list_models()` que lê `status`/`args` |
| `providers/openai_compat.py:44` | Já suporta `api_key` + `api_key_env`; `llamacpp.py` já declara `LLAMACPP_API_KEY` | Só usar — autenticação **já está pronta** |
| `runner.py:152` `_run_model` | `cfg.unload_between` **já chama** `provider.unload()` | Passa a funcionar de verdade, sem mudar o runner |
| `runner.py:72-87` `RunConfig.to_dict()` | Allowlist **escrita à mão** | ⚠️ Campo novo que não for adicionado aqui **some** de todo relatório e run salvo |
| `catalog.py` | `weight_bytes()`, `kv_cache_bytes()`, `QUANT_GB_PER_B` | Base da heurística de `-ngl` |
| `doctor.py` | Dataclass `Check` + `run_checks()` | Ganha checagens de router (alcançável? autenticado? o que está carregado?) |
| `cli.py` | Subcomando = 3 edições | ⚠️ Incluir o nome em `_COMMANDS` (`cli.py:182`), senão vira `homebench run <nome>` |
| `models.py:14` `_pick()` | `from_dict` descarta chaves desconhecidas | Campos novos são retrocompatíveis com runs já salvos |

### Ponto-chave sobre os parâmetros

O servidor **já resolve os presets** e expõe o `argv` final em `status.args`. Ou seja, a base de
"parâmetros recomendados" **sai de graça** da API — a heurística só precisa cobrir modelos sem
preset. Isso reduz bastante o item 2 do roadmap original.

---

## 3b. Contrato da API — confirmado por teste de fumaça

Extraído do bundle do painel web (`/_app/immutable/bundle.*.js`) e **verificado ao vivo**
em 28/08/2026 contra `llama-vulkan` (`:8080`), com `qwen35-4b`:

```
POST /models/load    {"model": id, "extra_args": [...]}  → {"success": true}
POST /models/unload  {"model": id}                       → {"success": true}
GET  /v1/models      → data[].status.value ∈ {loaded, loading, unloaded}
                       data[].status.args  → argv já resolvido pelo servidor
GET  /models/sse     → stream de eventos de status
```

Ciclo medido: `unloaded` → load → **`loaded` em 4s** → geração → unload → `unloaded`.
Estado original restaurado.

**Duas consequências que encolhem o escopo:**

- **`extra_args` é exatamente o item 4 do fluxo desejado** ("parâmetros editáveis pelo usuário
  antes de carregar"). O router aceita args arbitrários de `llama-server` por carga — não é
  preciso construir nada para isso, só montar a lista.
- **`/models/sse` entrega o progresso ao vivo de graça** (item 6 do fluxo: "% de progresso,
  modelo atual"), sem polling e sem inventar mecanismo próprio.

## 4. Riscos

1. ~~`POST /models/load` não existe no build b10615~~ — **resolvido**. A rota existe; o `404
   File Not Found` anterior era o *arquivo do modelo* inexistente (sondagem com nome falso),
   não rota ausente. Não é preciso fallback nem sondagem de capacidade.
2. **São serviços de produção.** Open WebUI e Traefik compartilham esses containers. Descarregar
   um modelo em uso derruba a sessão de alguém. → Confirmação por padrão (já decidido) + checar
   requisição em voo antes de descarregar.
3. **`--models-max 2`**: dois modelos podem estar residentes. Medição limpa exige descarregar
   **o outro também**, não só garantir que o alvo está carregado.
4. **`api-key.txt` é segredo.** Ler de env/arquivo, nunca logar, nunca commitar.
5. **Piso Python 3.9**, CI em 3.9–3.12, sem dependência nova (`httpx` já está lá).
6. **Contagem de tokens em modelos de raciocínio.** No teste de fumaça, `qwen35-4b` devolveu
   `content: ''` com `completion_tokens: 10` — os tokens foram para `reasoning_content`. O
   parser de stream do homebench (`providers/openai_compat.py:130`) só lê `delta.content` e
   só cai no `usage` quando o servidor manda. Num benchmark de **tok/s isso subestima a taxa**
   em qualquer modelo com raciocínio ligado. → Investigar na fase de design; provavelmente
   contar `reasoning_content` também. Vários presets aqui usam `jinja`/`reasoning`.

---

## 5. Execução com a skill TLC (máximo 3 subagentes)

Estrutura pretendida — os subagentes rodam **estritamente em sequência**, então nunca há mais de
um vivo ao mesmo tempo, e a sessão coordenadora não acumula contexto de implementação:

| # | Papel | Conteúdo | Contexto recebido |
| --- | --- | --- | --- |
| 1 | Batch worker | Fase 1 (cliente do router + sondagem) e Fase 2 (parâmetros) | Só as tarefas do seu batch + `spec.md`/`design.md` |
| 2 | Batch worker | Fase 3 (manager + integração no provider) e Fase 4 (CLI + doctor) | Idem |
| 3 | **Verifier** | Checagem ancorada na spec + sensor de discriminação | `spec.md` + diff, sem herdar o modelo mental do autor |

A coordenadora lê apenas `spec.md` e `tasks.md`, recebe de cada worker um resumo compacto
(tarefas, hashes de commit, contagem de testes, desvios) e atualiza `tasks.md`. Artefatos em
`.specs/features/model-lifecycle/`.

---

## 6. Verificação

- **Testes automatizados**: `pytest -q`, com `pytest-httpx` simulando o router — sem servidor
  vivo, seguindo a convenção do repo (`conftest.py` já isola `HOMEBENCH_HOME`).
  Casos: rota `load` ausente → fallback; `unload` de modelo inexistente; dois modelos
  residentes; 401 sem chave.
- **Teste de fumaça ao vivo** — **autorizado pelo usuário**. Contra `:8080` e `:8081`, com o
  menor modelo (`qwen35-4b`, 2,8 GB). Ciclo completo, uma vez:
  `GET /v1/models` (confirma `unloaded`) → carrega → `GET /v1/models` (confirma `loaded`) →
  gera 5 tokens → `POST /models/unload` → `GET /v1/models` (confirma volta a `unloaded`).
  É o que resolve o risco nº 1: qual mecanismo de carregamento realmente funciona neste build.
- **Não regressão**: `pytest -q` completo nos 3.9–3.12 do CI, mais `homebench --no-quality`
  ponta a ponta.

---

## 7. Próximo passo

Rodar a fase **Specify** da skill `tlc-spec-driven` para transformar este plano em
`spec.md` com critérios de aceite em EARS, e então `design.md` / `tasks.md`.
