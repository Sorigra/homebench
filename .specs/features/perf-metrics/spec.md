# Métricas de Performance Bruta Specification

## Problem Statement

O leaderboard do homebench reporta um único `tok/s` medido no cliente, contando apenas
`delta.content` num prompt curto. Isso produz três defeitos numa fork cujo propósito é
performance bruta: modelos de raciocínio saem **zerados** (todo o texto vai em
`reasoning_content` — `Ornith-1.5-35B-A3B-Q8` reportou `0.00 tok/s` onde o real é `54.03`);
prefill e decode ficam fundidos num número só, escondendo que são regimes com ordens de
grandeza diferentes (2 714 vs 95 tok/s em `gemma4-e2b`); e tudo é medido em contexto ~zero,
onde nenhum uso real acontece — o decode do mesmo modelo cai 23% em 32k e o prefill cai 33%.

## Goals

- [ ] Nenhum modelo residente que gera tokens reporta `0.00 tok/s`.
- [ ] Prefill e decode aparecem como métricas separadas, com origem no `timings` do servidor
      quando disponível.
- [ ] Cada modelo é medido em 3 profundidades de contexto (0 / 8192 / 32768) numa mesma run.
- [ ] Runs salvos antes desta feature continuam carregando em `history` e `diff`.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Medir prefill/decode em providers não-llama.cpp com timings server-side | Só o llama.cpp expõe `timings`; os demais caem no caminho cliente já especificado (PERF-06) |
| Profundidades configuráveis por modelo | `--depths` é global na run; per-modelo é complexidade sem demanda |
| Reportar tokens de raciocínio como métrica de qualidade separada | Esta feature é de medição de velocidade; qualidade é secundária nesta fork |
| Varredura de concorrência em cada profundidade | `homebench throughput` já é um comando à parte; cruzar os dois eixos multiplica o tempo de run |
| Comparar Vulkan vs ROCm nas 3 profundidades numa run | Depende do MLC-15 (CLI de dois hosts), adiado em AD-006 |
| Reescrever o score `Value` | Decisão do usuário: `Value` continua alimentado pelo decode em profundidade 0 |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Forma do resultado por profundidade | `ModelReport.speed` continua sendo a medição em profundidade 0; a varredura entra num campo novo `depth_results: List[DepthMetrics]` | Mantém `history.py`, `score.py` e o HTML lendo `speed.tokens_per_sec` sem mudança, e faz runs antigos (sem o campo) carregarem com lista vazia | y |
| Tokens de raciocínio contam no tok/s | Sim, contam como tokens gerados | Custam a mesma compute e é isso que uma ferramenta de performance bruta mede; a separação content/reasoning fica registrada em campos próprios | y |
| Texto entregue aos graders de qualidade | Só `content`, nunca `reasoning_content` | O raciocínio não é a resposta; misturá-lo quebraria graders determinísticos como `valid_json` | y |
| Origem dos números de prefill/decode | `timings` do servidor quando presente; cronometragem no cliente como fallback | O servidor mede sem ruído de rede e de parsing; verificado ao vivo no build `b10664` | y |
| Controle de cache de prompt na varredura | `cache_prompt: false` em toda geração de medição | Sem isso a 2ª medição do mesmo prompt reusa KV e o prefill mente (2 540 vs 1 478 tok/s, medido ao vivo) | y |
| Profundidade maior que o contexto do modelo | Pula aquela profundidade, registra o motivo, e as demais profundidades do modelo seguem | Falhar o modelo inteiro perderia as medições válidas que já rodaram | y |
| Unidade de "profundidade" | Tokens de prompt, medidos por `prompt_n` do servidor (ou `usage.prompt_tokens`) | É o número que o servidor de fato processou; contar palavras erra ~13% (medido: 1 200 palavras → 1 355 tokens) | y |
| Tolerância entre profundidade pedida e obtida | ±10% do alvo, gravada a profundidade real | O prompt sintético não acerta a contagem exata de tokens de um tokenizer arbitrário | y |
| Ordenação do leaderboard e score `Value` | Decode em profundidade 0 | Escolhido pelo usuário: é o número comparável com o que se publica por aí | y |
| Layout da tabela | Uma linha por (modelo, profundidade) | Escolhido pelo usuário | y |
| Varredura ligada por padrão | Sim: `0,8192,32768`; `--depths 0` volta ao comportamento antigo | Escolhido pelo usuário | y |

**Open questions:** none - all resolved or logged above.

---

## User Stories

### P1: tok/s que não zera em modelo de raciocínio ⭐ MVP

**User Story**: Como quem faz benchmark de performance, quero que modelos de raciocínio
reportem sua velocidade real, para que uma linha zerada signifique falha e não um formato
de resposta diferente.

**Why P1**: É o defeito que motivou a feature. Hoje `Ornith-1.5-35B-A3B-Q8` sai `0.00 tok/s`
com cara de resultado válido, sem erro nem aviso.

**Acceptance Criteria**:

1. WHEN um chunk de stream traz `delta.reasoning_content` não vazio THEN o sistema SHALL tratá-lo como token gerado para efeito de TTFT, tempo de decode e contagem de tokens.
2. WHEN o primeiro token de uma geração chega em `reasoning_content` THEN o sistema SHALL registrar o TTFT nesse instante.
3. The system SHALL expor a contagem de tokens de `content` e de `reasoning_content` em campos separados de `SpeedMetrics`.
4. WHEN uma geração é usada para avaliação de qualidade THEN o sistema SHALL entregar ao grader apenas o texto de `content`.
5. IF uma geração termina com zero tokens de saída em `content` e em `reasoning_content` THEN o sistema SHALL registrar um aviso no `ModelReport` identificando a geração como vazia.

**Independent Test**: rodar `homebench run -m Ornith-1.5-35B-A3B-Q8 --no-quality --depths 0`
e ver um tok/s diferente de zero na coluna de decode.

---

### P2: prefill e decode como métricas separadas

**User Story**: Como quem dimensiona hardware, quero ver o custo de processar a entrada
separado do custo de gerar a saída, para saber se um modelo é limitado por compute ou por
banda de memória.

**Why P2**: Depende da correção de timing da P1 para os números serem confiáveis, mas é a
mudança de tabela que o usuário pediu.

**Acceptance Criteria**:

1. WHERE o servidor devolve um objeto `timings` no stream THEN o sistema SHALL usar `prompt_per_second` como taxa de prefill e `predicted_per_second` como taxa de decode.
2. WHERE o servidor não devolve `timings` THEN o sistema SHALL derivar a taxa de decode da cronometragem no cliente e SHALL deixar a taxa de prefill sem valor em vez de estimá-la.
3. The system SHALL gravar `prompt_eval_s` e a taxa de prefill em `SpeedMetrics`, preenchendo o campo `prompt_eval_s` que hoje existe e nunca é escrito.
4. WHEN o leaderboard é renderizado THEN o sistema SHALL exibir prefill e decode em duas colunas distintas.
5. IF a taxa de prefill não está disponível THEN o sistema SHALL exibir `–` naquela célula em vez de zero.

**Independent Test**: rodar contra `127.0.0.1:8080` e conferir que a coluna de prefill traz
um valor na ordem de milhares e a de decode na ordem de dezenas.

---

### P3: varredura de profundidade de contexto

**User Story**: Como quem escolhe um modelo para uso real, quero ver a velocidade em 0, 8192
e 32768 tokens de contexto, para escolher com base na degradação e não só no melhor caso.

**Why P3**: É a maior mudança de superfície (forma do resultado, tabela, tempo de run) e
depende das duas anteriores para medir a coisa certa.

**Acceptance Criteria**:

1. The system SHALL medir cada modelo nas profundidades `0`, `8192` e `32768` tokens de prompt por padrão.
2. WHEN `--depths` recebe uma lista de inteiros THEN o sistema SHALL medir exatamente essas profundidades, na ordem dada.
3. WHEN uma profundidade maior que zero é medida THEN o sistema SHALL construir um prompt sintético cuja contagem de tokens fique dentro de ±10% do alvo e SHALL gravar a profundidade real obtida.
4. The system SHALL enviar `cache_prompt: false` em toda geração de medição, para que o prefill não seja lido de KV-cache reusado.
5. WHEN uma profundidade é medida THEN o sistema SHALL gravar prefill, decode, TTFT e profundidade real num `DepthMetrics` próprio dentro do `ModelReport`.
6. IF o servidor recusa a requisição porque o contexto excede o do modelo THEN o sistema SHALL pular apenas aquela profundidade, registrar o motivo em `ModelReport.warnings` e SHALL prosseguir com as demais profundidades daquele modelo.
7. WHEN o leaderboard é renderizado THEN o sistema SHALL emitir uma linha por par (modelo, profundidade), com a profundidade em coluna própria.
8. The system SHALL ordenar o leaderboard e calcular o score `Value` pela taxa de decode na menor profundidade medida do modelo.

**Independent Test**: rodar `homebench run -m gemma4-e2b --no-quality` sem flags e ver três
linhas para o modelo, com decode decrescente conforme a profundidade cresce.

---

### P3: compatibilidade de histórico e superfícies de saída

**User Story**: Como quem acompanha regressões, quero que runs salvos antes desta mudança
continuem abrindo em `history` e `diff`, para não perder a linha do tempo.

**Why P3**: Requisito de não-regressão; sem superfície nova própria.

**Acceptance Criteria**:

1. WHEN um run salvo sem o campo de profundidades é carregado THEN o sistema SHALL produzir um `ModelReport` válido com lista de profundidades vazia.
2. WHEN um `ModelReport` não tem profundidades THEN o leaderboard SHALL renderizar uma única linha para aquele modelo, sem coluna de profundidade preenchida.
3. The system SHALL manter `homebench diff` comparando a taxa de decode na profundidade 0 entre dois runs.
4. WHEN o relatório é exportado em Markdown, JSON ou HTML THEN o sistema SHALL incluir as mesmas linhas por profundidade que o leaderboard do terminal.

**Independent Test**: `homebench history` e `homebench diff` seguem funcionando sobre os runs
já salvos em `~/.homebench/runs/`.

---

## Edge Cases

- IF um modelo de raciocínio consome todo o `max_tokens` em `reasoning_content` sem emitir `content` THEN o sistema SHALL reportar a velocidade normalmente e SHALL deixar o texto de resposta vazio.
- IF `--depths` recebe um valor não inteiro ou negativo THEN o sistema SHALL abortar com mensagem indicando o valor inválido, antes de carregar qualquer modelo.
- IF `--depths` recebe uma lista vazia THEN o sistema SHALL tratá-la como `0`.
- IF duas profundidades pedidas resolvem para o mesmo prompt sintético THEN o sistema SHALL medir cada uma assim mesmo, sem deduplicar.
- WHEN a varredura roda com `--repeat > 1` THEN o sistema SHALL repetir a medição dentro de cada profundidade, não a varredura inteira.
- IF o `timings` do servidor traz `cache_n` maior que zero numa medição THEN o sistema SHALL registrar aviso de que o prefill daquele ponto pode estar contaminado por cache.
- IF a construção do prompt sintético não alcança a profundidade alvo dentro de ±10% THEN o sistema SHALL medir mesmo assim e SHALL gravar a profundidade real, nunca a pedida.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| PERF-01 | P1: tok/s de raciocínio | T4 | Pending |
| PERF-02 | P1: tok/s de raciocínio | T4 | Pending |
| PERF-03 | P1: tok/s de raciocínio | T1, T4 | Pending |
| PERF-04 | P1: tok/s de raciocínio | T4 | Pending |
| PERF-05 | P1: tok/s de raciocínio | Design | Pending |
| PERF-06 | P2: prefill vs decode | T5 | Pending |
| PERF-07 | P2: prefill vs decode | T5 | Pending |
| PERF-08 | P2: prefill vs decode | T5 | Pending |
| PERF-09 | P2: prefill vs decode | Design | Pending |
| PERF-10 | P3: varredura de profundidade | Design | Pending |
| PERF-11 | P3: varredura de profundidade | T3, T16 | Pending |
| PERF-12 | P3: varredura de profundidade | Design | Pending |
| PERF-13 | P3: varredura de profundidade | T2, T6, T9 | Pending |
| PERF-14 | P3: varredura de profundidade | Design | Pending |
| PERF-15 | P3: varredura de profundidade | Design | Pending |
| PERF-16 | P3: compatibilidade e saídas | T1, T2, T17 | Pending |
| PERF-17 | P3: compatibilidade e saídas | Design | Pending |

**Mapeamento AC → ID:** PERF-01..05 = P1 AC1..AC5 · PERF-06..09 = P2 AC1..AC4 (P2 AC5 dobra em
PERF-09) · PERF-10..15 = P3-varredura AC1..AC8 (AC4 dobra em PERF-12, AC8 em PERF-15) ·
PERF-16..17 = P3-compat AC1..AC4.

**Coverage:** 17 total, 0 mapeados para tasks, 17 não mapeados ⚠️ (a mapear na fase Tasks)

---

## Success Criteria

- [ ] `Ornith-1.5-35B-A3B-Q8` reporta decode ≈ 54 tok/s em profundidade 0, e não `0.00`.
- [ ] `gemma4-e2b` mostra três linhas com decode decrescente (≈95 → ≈83 → ≈73 tok/s).
- [ ] A coluna de prefill mostra ≈2 700 tok/s em profundidade 0 para `gemma4-e2b`.
- [ ] Todos os runs em `~/.homebench/runs/` salvos antes da feature continuam abrindo em `homebench history`.
- [ ] Suíte de testes verde nas versões de Python do CI, sem rede.
