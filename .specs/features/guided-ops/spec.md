# Guided Ops Specification

## Problem Statement

O caminho cotidiano desta fork ainda é um `docs/USO.md` de flags, exports e subcomandos.
Quem opera a máquina não é desenvolvedor: precisa instalar sem montar venv na mão, e depois
navegar modelos, contexto, tipo de teste e estado do router como numa BIOS, não como numa CLI.
A TUI atual só mostra o leaderboard **depois** que o run já foi escolhido por flags. Falta o
instalador e o painel de planejamento.

## Goals

- [ ] `./setup.sh` instala só o homebench, grava config e deixa um executável chamável.
- [ ] `homebench` sem argumentos, no terminal, abre o painel BIOS (não dispara o run sozinho).
- [ ] Dali dá para planejar, confirmar descarga, rodar o leaderboard existente, ver Doctor e Histórico.

## Out of Scope

Explicitamente excluído. Documentado para evitar scope creep.

| Feature | Reason |
| --- | --- |
| Instalar ou atualizar llama.cpp / ROCm / Docker | Operador escolheu “só o homebench”; AD-001 proíbe orquestrar o container |
| `sudo`, systemd, restart de container | AD-001 e `AGENTS.md` |
| Throughput na TUI | Recorte do MVP: permanece `homebench throughput` |
| Painel GPU AMD ao vivo | Adiado desde `model-lifecycle`; o híbrido é layout, não VRAM |
| `diff` / `report` / `fit` / `tasks` na TUI | Fora do menu BIOS deste corte |
| Wizard de 7 telas do doc de contexto | Substituído por BIOS multi-tela |
| `homebench setup` em Python | O pedido é `setup.sh` |
| Download de modelos | Já fora no doc de contexto |
| Campo livre de profundidade | Só os três toggles padrão neste corte |
| Interface web | A lógica fica headless para não travar isso depois |

---

## Assumptions & Open Questions

Toda ambiguidade resolvida ou registrada aqui.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Formato da tela | Híbrido: faixa de status + várias telas tipo BIOS | Escolhido pelo operador (item 1) | y |
| Alcance do instalador | Só homebench (venv, pip, config, lançador, doctor de leitura) | Escolhido pelo operador (item 2) | y |
| Recorte do painel | Planejar, Rodar, Doctor, Histórico; throughput na CLI | Escolhido pelo operador (item 3, 2026-09-10) | y |
| Comando sem argumentos | Argv vazio + TTY → painel; sem TTY → `run` | Escolhido pelo operador (item 4); pytest não é TTY | y |
| Defaults do setup | host `http://127.0.0.1:8080`; chave `~/llm-server/llama/api-key.txt`; modelos `/home/eskudo/ai-models` | Ambiente Strix Halo já documentado em `docs/USO.md` | y |
| Chave da API no disco | Só o **caminho** do arquivo em `config.json`; nunca o valor | `AGENTS.md` e AD-001: nunca logar nem commitar a chave | y |
| Precedência de config | Variável de ambiente ganha de `config.json` | Permite override pontual sem editar o arquivo | y |
| Profundidades no Planejar | Toggles independentes `0`, `8192`, `32768` | São o default atual de `--depths`; campo livre adiado | y |
| Tipo de teste | Três opções exclusivas: só velocidade, só qualidade, os dois | Mapeia `--no-quality` / `--no-speed` / nenhum dos dois | y |
| Idioma da UI do painel e do setup | Português, frases curtas | Agent's discretion confirmada no context | y |
| Router down no setup | Instala mesmo assim; checagem fica `fail` | Operador: não desfazer; não subir Docker | y |
| Lançador | Wrapper em `~/.local/bin/homebench` apontando ao `.venv` do repo | “chamar o executável” depois de instalado | y |
| AD-001 / AD-002 / AD-005 / AD-007 | Continuam valendo | Já são decisão de projeto | y |

**Open questions:** none — todas resolvidas ou registradas na tabela acima.

---

## Varredura de dimensões implícitas (obrigatória para escopo Complex)

| Dimensão | Resolução |
| --- | --- |
| Validação de entrada & limites | GOPS-13 (plano sem modelo ou sem tipo de teste recusa Rodar); GOPS-01 (Python &lt; 3.9 aborta antes do venv) |
| Falha / falha parcial | GOPS-04 (router down não desfaz install); GOPS-10 (faixa mostra down, painel não crasha); GOPS-03 (lançador não gravável não falha o install) |
| Idempotência / retry / duplicata | GOPS-05 (setup.sh pode rodar de novo: reusa `.venv`, sobrescreve `config.json`) |
| Fronteiras de auth & rate limit | GOPS-11 (UI e logs nunca mostram o valor da chave). Rate limit: **N/A** — router local, um operador |
| Concorrência / ordenação | **N/A** — um painel por processo; não dispara dois runs ao mesmo tempo neste corte |
| Ciclo de vida de dados / expiração | GOPS-14 / GOPS-15 (`last_plan` em `config.json`; sem TTL; ids desaparecidos são descartados) |
| Observabilidade | GOPS-09 (faixa de status); GOPS-19 (Doctor reusa `run_checks`) |
| Falha de dependência externa | GOPS-04, GOPS-10, GOPS-19 (doctor `fail` se o router não autentica ou não responde) |
| Integridade de transição de estado | GOPS-16 / GOPS-17 (recusar confirmação volta ao painel sem unload e sem leaderboard); GOPS-06 vs GOPS-07 (TTY decide painel vs `run`) |

---

## User Stories

### P1: Instalar com perguntas ⭐ MVP

**User Story**: Como operador da mini PC, quero um `setup.sh` que pergunta o necessário e instala
o homebench, para não montar venv, pip e exports na mão.

**Why P1**: Sem isso o painel não tem config persistida e o `docs/USO.md` continua sendo o
caminho real.

**Acceptance Criteria**:

1. WHEN `setup.sh` roda sem `--defaults` num TTY THEN o sistema SHALL perguntar host do router, caminho do arquivo da chave e diretório de modelos, oferecendo os três defaults se o operador só apertar Enter.
2. WHEN `setup.sh` é invocado com `--defaults` THEN o sistema SHALL usar `http://127.0.0.1:8080`, `~/llm-server/llama/api-key.txt` e `/home/eskudo/ai-models` sem perguntar.
3. IF `python3` for mais antigo que 3.9 THEN o sistema SHALL sair com código diferente de 0 antes de criar `.venv`.
4. WHEN o `pip install -e .` concluir THEN o sistema SHALL gravar `$HOMEBENCH_HOME/config.json` (default `~/.homebench/config.json`) com host, caminho da chave e diretório de modelos, **sem** o valor da chave.
5. WHEN `~/.local/bin` existir e for gravável THEN o sistema SHALL instalar um lançador `homebench` que executa o `homebench` do `.venv` do repositório.
6. IF `~/.local/bin` não existir ou não for gravável THEN o sistema SHALL imprimir o caminho `.venv/bin/homebench` e mesmo assim sair 0 se venv e config tiverem sido gravados.
7. IF a checagem de leitura do router falhar THEN o sistema SHALL manter venv e config, reportar a falha, e **não** invocar Docker, `sudo` nem systemd.
8. The system SHALL recusar `docker`, `sudo` e `systemctl` em qualquer ramo do `setup.sh`.
9. WHEN `setup.sh` roda de novo no mesmo repo THEN o sistema SHALL reutilizar o `.venv` existente e sobrescrever `config.json`.

**Independent Test**: `./setup.sh --defaults` num diretório temporário com `HOME` isolado cria `.venv`, `config.json` sem a chave, e sai 0 mesmo com o router inacessível.

---

### P1: Abrir o painel no executável ⭐ MVP

**User Story**: Como operador, quero chamar `homebench` sem argumentos e cair no painel, para
não precisar lembrar subcomandos.

**Why P1**: É a promessa “depois de instalado é só chamar o executável”.

**Acceptance Criteria**:

1. WHEN `homebench` é invocado com argv vazio e stdin **e** stdout são TTY THEN o sistema SHALL abrir o painel e **não** iniciar um benchmark.
2. WHEN `homebench` é invocado com argv vazio e stdin ou stdout **não** é TTY THEN o sistema SHALL comportar-se como `homebench run` (caminho `plainui` / CI).
3. WHEN `homebench` é invocado com qualquer argumento THEN o sistema SHALL manter o roteamento CLI atual (`run`, `doctor`, `history`, `throughput`, flags).
4. WHEN o subcomando `panel` é invocado THEN o sistema SHALL abrir o painel.
5. IF o subcomando `panel` for invocado sem TTY THEN o sistema SHALL sair com código diferente de 0 e uma mensagem dizendo que o painel precisa de terminal.

**Independent Test**: `_inject_default_command([])` num pytest (não-TTY) continua `["run"]`; com stdin/stdout TTY vira `["panel"]`; `homebench doctor` não abre o painel.

---

### P1: Faixa de status do router ⭐ MVP

**User Story**: Como operador, quero ver na faixa se o llama.cpp está no ar, o build e quais
modelos estão residentes, para não abrir outra aba de `curl`.

**Why P1**: Substitui a parte “status do llama.cpp” do `docs/USO.md` sem GPU ao vivo.

**Acceptance Criteria**:

1. WHILE o painel mostra Planejar, Doctor ou Histórico o sistema SHALL exibir na faixa o host, `up` ou `down`, e — se `up` — `build_info` e a lista de ids residentes.
2. IF o router estiver inalcançável ou a autenticação falhar THEN a faixa SHALL mostrar `down` e o host, e o painel SHALL permanecer utilizável (Doctor/Histórico/Planejar não crasham).
3. The system SHALL NUNCA renderizar o valor da chave de API na faixa nem em qualquer tela do painel.

**Independent Test**: com um cliente fake down, a faixa contém `down` e o host; a chave usada no teste não aparece no texto renderizado.

---

### P1: Planejar modelos, profundidade e tipo ⭐ MVP

**User Story**: Como operador, quero marcar quais modelos rodam, quais profundidades e se o
teste é velocidade, qualidade ou os dois, para não montar `-m` e `--depths` na mão.

**Why P1**: É o núcleo do planejamento tipo BIOS.

**Acceptance Criteria**:

1. WHEN o operador abre Planejar THEN o sistema SHALL listar os ids de modelo que o router (ou o provider) reporta, cada um marcável.
2. WHEN o operador liga ou desliga profundidades THEN o plano SHALL conter só o subconjunto escolhido dentre `0`, `8192` e `32768`, na ordem numérica crescente.
3. WHEN o operador escolhe o tipo de teste THEN o plano SHALL ficar em exatamente um de: só velocidade (`run_speed=true`, `run_quality=false`), só qualidade (`run_speed=false`, `run_quality=true`), ou os dois (`true`, `true`).
4. IF o operador dispara Rodar com zero modelos marcados THEN o sistema SHALL recusar, permanecer no painel, e mostrar que é preciso ao menos um modelo.
5. IF o operador dispara Rodar com nenhuma profundidade marcada THEN o sistema SHALL recusar, permanecer no painel, e mostrar que é preciso ao menos uma profundidade.
6. WHEN um plano válido é deixado em Planejar THEN o sistema SHALL gravar `last_plan` em `config.json`.
7. WHEN o painel abre e `last_plan` existe THEN o sistema SHALL restaurar as marcações cujo id ainda existe na lista atual e SHALL descartar ids que desapareceram.

**Independent Test**: marcar dois modelos e só a profundidade `0`, sair e reabrir o plano headless a partir do JSON: os dois ids e `[0]` voltam; um id removido do catálogo some da restauração.

---

### P1: Rodar com confirmação e leaderboard existente ⭐ MVP

**User Story**: Como operador, quero disparar o run a partir do painel e ver o leaderboard de
sempre, sem a ferramenta descarregar um modelo de terceiro sem perguntar.

**Why P1**: Fecha o ciclo planejar → medir. Reusa o que já existe.

**Acceptance Criteria**:

1. WHEN o operador dispara Rodar com plano válido e há modelos residentes **fora** desse plano THEN o sistema SHALL listar esses ids e pedir confirmação antes de descarregar (AD-002 / AD-007).
2. IF o operador recusar a confirmação THEN o sistema SHALL voltar ao painel sem descarregar nada e sem abrir o leaderboard.
3. WHEN a confirmação é aceita ou não é necessária THEN o sistema SHALL entregar `Runner` + lista `ModelInfo` do plano à TUI de leaderboard já existente em `tui/app.py`.
4. The system SHALL NÃO reimplementar medição de velocidade ou qualidade dentro do painel.

**Independent Test**: plano com um modelo, fake router com um residente estrangeiro, confirmer que devolve false: `unload` não é chamado e `run_tui` não é chamado.

---

### P1: Doctor e Histórico no mesmo programa ⭐ MVP

**User Story**: Como operador, quero ver o diagnóstico e os runs salvos em telas do painel, para
não sair para `homebench doctor` e `homebench history`.

**Why P1**: Recorte do item 3. Sem isso o `USO.md` continua obrigatório para duas operações do dia a dia.

**Acceptance Criteria**:

1. WHEN o operador abre Doctor THEN o sistema SHALL mostrar cada `Check` de `doctor.run_checks` com nome, `status` (`ok`/`warn`/`fail`/`info`) e `detail`.
2. WHILE a tela Doctor está aberta o sistema SHALL NÃO carregar, descarregar nem alterar config.
3. WHEN o operador abre Histórico THEN o sistema SHALL listar os runs de `history.list_runs`, mais novo primeiro, com data, provider, label (se houver) e nomes dos modelos.
4. IF não houver runs salvos THEN o sistema SHALL mostrar que ainda não há runs e permanecer no painel, com código de saída 0 se o operador só consultar e sair.

**Independent Test**: `run_checks` fake com dois checks (`ok` e `fail`) aparece os dois na snapshot da tela; `list_runs` vazio produz a mensagem de vazio, não exceção.

---

### P2: Caminho feliz no `docs/USO.md`

**User Story**: Como operador, quero que o guia comece em `setup.sh` + painel, para achar o
fluxo certo sem ler 10 seções de flags.

**Why P2**: O painel já resolve o uso; o doc só precisa deixar de ser o obstáculo.

**Acceptance Criteria**:

1. WHEN `docs/USO.md` for o guia desta fork THEN a primeira seção de uso SHALL ser `./setup.sh` seguido de `homebench` no terminal.
2. The system SHALL manter as flags avançadas (`throughput`, `--depths` livre, vLLM, live tests) **depois** do caminho feliz, não no topo.

**Independent Test**: as primeiras 40 linhas de `docs/USO.md` citam `setup.sh` e o painel; `throughput` não aparece antes dessa seção.

---

## Edge Cases

- IF `config.json` estiver ausente ou JSON inválido THEN o sistema SHALL ignorar o arquivo, cair em env/defaults, e **não** crashar o painel nem o CLI.
- IF o arquivo da chave apontado por `api_key_file` não existir THEN o sistema SHALL seguir (status/doctor `fail` de autenticação quando o router exigir chave); o setup não apaga o caminho gravado.
- IF variáveis `LLAMACPP_HOST`, `LLAMACPP_API_KEY` ou `HOMEBENCH_MODEL_DIR` estiverem definidas THEN o sistema SHALL usá-las no lugar dos campos correspondentes de `config.json`.
- IF `setup.sh` for invocado de outro diretório THEN o sistema SHALL operar no diretório do próprio script (raiz do repo), não no cwd do operador.
- IF o catálogo de modelos estiver vazio THEN Planejar SHALL mostrar lista vazia e Rodar permanecer recusado por GOPS-13.
- WHEN dois ou mais modelos estão marcados THEN o plano SHALL conservar todos, não só o primeiro (lista, não item único).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| GOPS-01 | P1: Instalar com perguntas | Tasks | In Tasks |
| GOPS-02 | P1: Instalar com perguntas | Tasks | In Tasks |
| GOPS-03 | P1: Instalar com perguntas | Tasks | In Tasks |
| GOPS-04 | P1: Instalar com perguntas | Tasks | In Tasks |
| GOPS-05 | P1: Instalar com perguntas | Tasks | In Tasks |
| GOPS-06 | P1: Abrir o painel no executável | Tasks | In Tasks |
| GOPS-07 | P1: Abrir o painel no executável | Tasks | In Tasks |
| GOPS-08 | P1: Abrir o painel no executável | Tasks | In Tasks |
| GOPS-09 | P1: Faixa de status do router | Tasks | In Tasks |
| GOPS-10 | P1: Faixa de status do router | Tasks | In Tasks |
| GOPS-11 | P1: Faixa de status do router | Tasks | In Tasks |
| GOPS-12 | P1: Planejar modelos, profundidade e tipo | Tasks | In Tasks |
| GOPS-13 | P1: Planejar modelos, profundidade e tipo | Tasks | In Tasks |
| GOPS-14 | P1: Planejar modelos, profundidade e tipo | Tasks | In Tasks |
| GOPS-15 | P1: Planejar modelos, profundidade e tipo | Tasks | In Tasks |
| GOPS-16 | P1: Rodar com confirmação e leaderboard existente | Tasks | In Tasks |
| GOPS-17 | P1: Rodar com confirmação e leaderboard existente | Tasks | In Tasks |
| GOPS-18 | P1: Rodar com confirmação e leaderboard existente | Tasks | In Tasks |
| GOPS-19 | P1: Doctor e Histórico no mesmo programa | Tasks | In Tasks |
| GOPS-20 | P1: Doctor e Histórico no mesmo programa | Tasks | In Tasks |
| GOPS-21 | P2: Caminho feliz no docs/USO.md | Tasks | In Tasks |

**ID format:** `GOPS-NN`

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 21 total, 21 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] Um operador consegue ir de repo clonado a painel com `./setup.sh` + `homebench`, sem export manual.
- [ ] Argv vazio no TTY não dispara benchmark.
- [ ] pytest (não-TTY) continua tratando argv vazio como `run`.
- [ ] Recusar unload não descarrega e não abre leaderboard.
- [ ] Valor da API key nunca aparece em config, faixa, Doctor ou Histórico.
