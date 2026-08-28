# Model Lifecycle (llama.cpp router) Specification

## Problem Statement

O `homebench` mede performance assumindo que o servidor já está de pé com o modelo certo
carregado. Ele não sabe o que está carregado, não descarrega nada, e não controla os parâmetros
de carga. Num benchmark isso é um defeito de medição, não uma comodidade: se o modelo errado
estiver residente, ou se dois modelos estiverem disputando VRAM, os números de tok/s e memória
saem errados sem nenhum aviso. O ambiente alvo agrava isso — o router está configurado com
`--models-max 2`, então dois modelos residentes é um estado normal, não excepcional.

O `llama.cpp` em modo router já expõe todo o ciclo de vida por HTTP. O que falta é o
`homebench` usar isso.

## Goals

- [ ] Antes de medir, o `homebench` sabe e reporta exatamente quais modelos estão residentes.
- [ ] O usuário consegue garantir que **só** o modelo alvo está carregado, com uma confirmação.
- [ ] Os parâmetros de carga efetivos ficam registrados junto com o resultado do benchmark.
- [ ] Zero gerenciamento de processo ou container — tudo via API do router.

## Out of Scope

Explicitamente excluído. Documentado para evitar scope creep.

| Feature | Reason |
| --- | --- |
| Painel de GPU AMD ao vivo | Feature seguinte; depende de sensor amdgpu, independente deste módulo |
| Perfis de teste (tamanhos de prompt/contexto) | Feature seguinte; não toca ciclo de vida |
| Fluxo guiado na TUI (boas-vindas → seleção → execução) | Feature seguinte; consome este módulo, não faz parte dele |
| Download de modelos | Fora de escopo declarado no doc de contexto |
| Subir/derrubar processo ou container `llama-server` | O router já é dono do ciclo de vida; mexer no container quebraria Open WebUI e Traefik |
| Suporte a lifecycle em Ollama / vLLM / LM Studio | Este módulo é específico do router llama.cpp; `ollama` já tem `unload()` próprio |
| Corrigir contagem de tokens de `reasoning_content` | Defeito real e adjacente, mas é de medição, não de ciclo de vida — vira feature própria (ver MLC-16) |

---

## Assumptions & Open Questions

Toda ambiguidade resolvida ou registrada aqui.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Controle via API do router, não processo/Docker | Cliente HTTP puro | Contrato verificado ao vivo; containers servem Open WebUI + Traefik em produção, mexer neles é destrutivo | y |
| Descarregar modelo já residente | Pede confirmação; flag `--force-unload` pula | Escolhido pelo usuário; evita derrubar sessão de terceiro no Open WebUI | y |
| Origem dos parâmetros recomendados | Híbrido: heurística + override JSON | Escolhido pelo usuário; o preset já resolvido pelo servidor serve de base gratuita | y |
| Escopo desta feature | Só ciclo de vida | Escolhido pelo usuário; demais itens viram features seguintes | y |
| Teste de fumaça contra serviço vivo | Autorizado, com modelos em `/home/ai-models` | Autorizado explicitamente pelo usuário | y |
| Como decidir "medição limpa" com `--models-max 2` | Descarregar **todos** os outros, não só garantir o alvo carregado | Um segundo modelo residente disputa VRAM e contamina tok/s e memória | y |
| Timeout de carga | 300 s, alinhado ao `RunConfig.timeout` existente | Modelos grandes (120B) demoram; reusa a convenção do repo em vez de criar constante nova | n |
| Onde guardar o override JSON de parâmetros | `$HOMEBENCH_HOME/load-params.json` | Mesma raiz do cache e do histórico; `conftest.py` já isola isso nos testes | n |
| Se `extra_args` inválido deve ser validado no cliente | Não — repassar e deixar o router recusar | O router é a autoridade sobre flags válidas do `llama-server`; validar no cliente duplicaria e desatualizaria | n |

**Open questions: none** — todas resolvidas ou registradas na tabela acima.

---

## Varredura de dimensões implícitas (obrigatória para escopo Large)

| Dimensão | Resolução |
| --- | --- |
| Validação de entrada & limites | MLC-02 (modelo inexistente), MLC-13 (`extra_args` repassado sem validação local) |
| Falha / falha parcial | MLC-05 (timeout de carga), MLC-06 (carga falha deixa estado consistente) |
| Idempotência / retry / duplicata | MLC-04 (carregar modelo já carregado é no-op bem-sucedido) |
| Fronteiras de auth & rate limit | MLC-07 (401/403 sem chave). Rate limit: **N/A** — router local, sem throttle |
| Concorrência / ordenação | MLC-03 (`--models-max`: descarrega os outros antes), MLC-08 (requisição em voo) |
| Ciclo de vida de dados / expiração | **N/A** — o módulo não persiste estado próprio; o que persiste é o resultado do run, já coberto pelo `history.py` existente |
| Observabilidade | MLC-09 (parâmetros efetivos gravados no resultado), MLC-12 (`doctor`) |
| Falha de dependência externa | MLC-10 (router inalcançável), MLC-11 (container reiniciando) |
| Integridade de transição de estado | MLC-01 (`unloaded`/`loading`/`loaded`), MLC-05 (espera sair de `loading`) |

---

## User Stories

### P1: Medição limpa garantida ⭐ MVP

**User Story**: Como quem roda o benchmark, quero que a ferramenta garanta que só o modelo alvo
está carregado antes de medir, para que os números não sejam contaminados por outro modelo
disputando VRAM.

**Why P1**: É a razão de existir do módulo. Sem isso, todo número que a ferramenta produz é
suspeito, e o usuário não tem como saber quando.

**Acceptance Criteria**:

1. WHEN o módulo consulta o router THEN o sistema SHALL reportar, para cada modelo, um estado
   dentre exatamente `loaded`, `loading` ou `unloaded`.
2. IF o modelo alvo não existe no router THEN o sistema SHALL falhar com `ProviderError` citando
   o id solicitado, sem carregar nada.
3. WHEN há outros modelos residentes além do alvo THEN o sistema SHALL descarregar todos os
   outros antes de medir.
4. WHEN o modelo alvo já está `loaded` com os mesmos parâmetros THEN o sistema SHALL tratar a
   carga como no-op bem-sucedida, sem descarregar e recarregar.
5. WHILE o modelo está em `loading` o sistema SHALL aguardar a transição para `loaded` por até
   300 segundos antes de declarar timeout.
6. IF a carga falhar ou expirar THEN o sistema SHALL propagar `ProviderError` e deixar o router
   sem modelo parcialmente carregado pelo módulo.
7. IF a chave de API estiver ausente ou incorreta THEN o sistema SHALL falhar com `ProviderError`
   dizendo que a autenticação foi recusada, sem expor o valor da chave.

**Independent Test**: com o router vivo, partindo de dois modelos residentes, rodar o fluxo e
observar `GET /v1/models` mostrando apenas o alvo como `loaded`.

---

### P1: Confirmação antes de descarregar ⭐ MVP

**User Story**: Como dono da máquina, quero ser avisado antes que a ferramenta descarregue um
modelo, para não derrubar sem querer uma sessão que alguém está usando no Open WebUI.

**Why P1**: Os mesmos containers servem produção. Descarregar sem avisar é uma ação destrutiva
para um terceiro, e o usuário escolheu explicitamente esse comportamento.

**Acceptance Criteria**:

1. WHEN o módulo precisa descarregar um modelo residente THEN o sistema SHALL exibir quais
   modelos serão descarregados e pedir confirmação antes de agir.
2. WHERE a flag `--force-unload` estiver presente o sistema SHALL descarregar sem pedir
   confirmação.
3. IF a entrada não for interativa e `--force-unload` estiver ausente THEN o sistema SHALL
   abortar com mensagem explicando como prosseguir, em vez de descarregar por conta própria.
4. IF o usuário recusar a confirmação THEN o sistema SHALL abortar sem descarregar nada e sem
   iniciar a medição.

**Independent Test**: rodar com um modelo residente e responder "não" — verificar que
`GET /v1/models` segue idêntico e que nenhum benchmark rodou.

---

### P1: `unload()` real no provider llamacpp ⭐ MVP

**User Story**: Como quem roda o benchmark com `--no-unload` desligado, quero que o homebench
realmente libere o modelo entre execuções, para que cada modelo seja medido sem o anterior
ocupando memória.

**Why P1**: `RunConfig.unload_between` já existe e já é chamado pelo runner, mas hoje é um no-op
herdado no provider llamacpp — a opção mente para o usuário.

**Acceptance Criteria**:

1. WHEN o runner chama `unload()` no provider llamacpp THEN o sistema SHALL enviar
   `POST /models/unload` para o modelo indicado.
2. IF o descarregamento falhar THEN o sistema SHALL registrar a falha sem interromper o run,
   preservando a convenção best-effort dos providers existentes.
3. The system SHALL manter `unload()` como no-op nos providers que não são router llama.cpp.

**Independent Test**: rodar `homebench -m modelA,modelB --no-quality` e observar via
`GET /v1/models` que `modelA` sai de `loaded` antes de `modelB` entrar.

---

### P2: Parâmetros de carga controláveis

**User Story**: Como quem afina performance, quero ver os parâmetros sugeridos e poder editá-los
antes de carregar, para comparar configurações (`-ngl`, contexto, flash attention) no mesmo modelo.

**Why P2**: É o que transforma a ferramenta de "mede o que está aí" em "mede o que eu quiser
testar". Não é MVP porque carregar sem `extra_args` já funciona — o router aplica os presets.

**Acceptance Criteria**:

1. WHEN o módulo resolve os parâmetros de um modelo THEN o sistema SHALL aplicar a precedência
   flag explícita > override JSON > preset do servidor > heurística > default do llama.cpp.
2. WHEN parâmetros extras forem fornecidos THEN o sistema SHALL enviá-los em `extra_args` no
   `POST /models/load`.
3. IF o router recusar os parâmetros THEN o sistema SHALL propagar a mensagem de erro do router
   sem reinterpretá-la.
4. WHEN um run termina THEN o sistema SHALL gravar os parâmetros de carga efetivos no resultado
   salvo, de modo que dois runs do mesmo modelo com parâmetros diferentes sejam distinguíveis.
5. WHERE não houver preset nem override para o modelo o sistema SHALL derivar uma sugestão de
   `-ngl` a partir do tamanho do arquivo e do orçamento de memória disponível.

**Independent Test**: carregar o mesmo modelo duas vezes com `-ngl` diferente e verificar que os
dois runs salvos registram valores distintos.

---

### P2: Inspeção e diagnóstico

**User Story**: Como usuário não desenvolvedor, quero um comando que me diga o que está
carregado e com quais parâmetros, para não precisar montar `curl` na mão.

**Why P2**: Substitui inspeção manual e é a porta de entrada para diagnosticar um benchmark
estranho — mas não bloqueia a medição em si.

**Acceptance Criteria**:

1. WHEN o usuário executar o subcomando de modelos THEN o sistema SHALL listar cada modelo com
   seu estado e, para os residentes, os parâmetros efetivos.
2. WHEN `doctor` rodar contra um provider router THEN o sistema SHALL incluir uma checagem de
   alcançabilidade e autenticação do router.
3. IF o router estiver inalcançável THEN o sistema SHALL reportar `fail` com o host tentado,
   sem stack trace.

**Independent Test**: `homebench models --provider llamacpp` mostra os 17 modelos com estado.

---

### P3: Comparar backends Vulkan vs ROCm

**User Story**: Como dono de um mini PC com dois backends sobre o mesmo hardware, quero medir o
mesmo modelo nos dois, para saber qual compila melhor para minha GPU.

**Why P3**: Alto valor para este ambiente específico, mas é consequência de tratar o host como
parâmetro — não exige mecanismo novo.

**Acceptance Criteria**:

1. WHEN dois hosts de router forem indicados THEN o sistema SHALL medir o mesmo modelo em cada um
   e apresentar os resultados lado a lado.

---

## Edge Cases

- IF o router responder 404 `File Not Found` em `POST /models/load` THEN o sistema SHALL
  interpretar como arquivo de modelo ausente, não como rota inexistente, e citar o id do modelo.
- IF o container do router reiniciar durante a medição THEN o sistema SHALL falhar o modelo
  corrente com `ProviderError` sem abortar os demais modelos do run.
- IF `--models-max` for atingido durante uma carga THEN o sistema SHALL descarregar o residente
  mais antigo antes de tentar de novo.
- WHEN houver requisição de inferência em voo no modelo a ser descarregado THEN o sistema SHALL
  avisar antes de pedir a confirmação.
- IF o arquivo de override JSON estiver malformado THEN o sistema SHALL avisar e seguir com a
  precedência restante, em vez de abortar o run.
- WHEN o mesmo modelo existir nos dois backends com ids diferentes THEN o sistema SHALL tratá-los
  como entradas independentes, sem deduplicar.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| MLC-01 | P1: Medição limpa | Design | Pending |
| MLC-02 | P1: Medição limpa | Design | Pending |
| MLC-03 | P1: Medição limpa | Design | Pending |
| MLC-04 | P1: Medição limpa | Design | Pending |
| MLC-05 | P1: Medição limpa | Design | Pending |
| MLC-06 | P1: Medição limpa | Design | Pending |
| MLC-07 | P1: Medição limpa | Design | Pending |
| MLC-08 | P1: Confirmação | Design | Pending |
| MLC-09 | P2: Parâmetros | Design | Pending |
| MLC-10 | P2: Inspeção | Design | Pending |
| MLC-11 | Edge: router reinicia | Design | Pending |
| MLC-12 | P2: Inspeção | Design | Pending |
| MLC-13 | P2: Parâmetros | Design | Pending |
| MLC-14 | P1: `unload()` real | Design | Pending |
| MLC-15 | P3: Comparar backends | - | Pending |
| MLC-16 | Fora de escopo: `reasoning_content` | - | Deferred |

**ID format:** `MLC-[NUMBER]`

**Coverage:** 15 ativos, 0 mapeados para tasks ainda, 1 diferido explicitamente.

---

## Success Criteria

- [ ] Partindo de dois modelos residentes, um run termina com apenas o alvo carregado — verificável por `GET /v1/models`.
- [ ] Nenhum modelo é descarregado sem confirmação ou sem `--force-unload`.
- [ ] Dois runs do mesmo modelo com `-ngl` diferente são distinguíveis no histórico salvo.
- [ ] `pytest -q` passa em Python 3.9–3.12 sem servidor vivo, com o router simulado por `pytest-httpx`.
- [ ] Nenhum container é iniciado, parado ou reiniciado pela ferramenta, em nenhum caminho de código.
