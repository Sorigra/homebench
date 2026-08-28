# perf-metrics — Validation Report

**Verdict: PASS**

**Spec**: `.specs/features/perf-metrics/spec.md`
**Diff range**: `0ee6812..fedde20` (código: `05cb261..fedde20`, 17 tarefas em 17 commits atômicos)
**Data**: 2026-08-28
**Gate**: `.venv/bin/python -m pytest -q` → **449 passed, 5 skipped, 0 failed** (454 coletados,
de uma linha de base de 378). `python -m build` + `twine check dist/*` → **PASSED** nos dois
artefatos.

**Ressalva de independência.** Esta validação foi feita inline pelo orquestrador, por decisão do
usuário (restrição de orçamento), não por um Verifier subagente. Autor ≠ verificador vale
parcialmente: o código e os testes foram escritos por três workers independentes, mas a spec foi
escrita por quem valida. Uma lacuna originada de erro na própria spec teria menor chance de ser
pega aqui do que num Verifier de contexto limpo.

---

## Checagem ancorada na spec (evidence-or-zero)

| Req | Critério | Evidência `file:line` + asserção | Resultado esperado pela spec | Coberto |
| --- | --- | --- | --- | --- |
| PERF-01 | `reasoning_content` conta como token gerado | `tests/test_providers.py:166` — `assert result.speed.ttft_s > 0` | taxa real, não zero | ✅ |
| PERF-02 | TTFT dispara no 1º token de raciocínio | `tests/test_providers.py:177` — `assert speed.ttft_s == 0.5` | o instante do token de raciocínio | ✅ |
| PERF-03 | contagens separadas de content e reasoning | `tests/test_providers.py:195-196` — `assert speed.content_tokens == 2` / `reasoning_tokens == 3` | campos distintos | ✅ |
| PERF-04 | grader recebe só `content` | `tests/test_providers.py:168` — `assert result.text == ""` | raciocínio nunca vira resposta | ✅ |
| PERF-05 | geração sem token nenhum vira aviso | `tests/test_runner_empty_generation.py:57-59` — `assert report.error is None`, `all("fast:1b" in w and "no tokens" in w ...)` | aviso, não erro nem `0.00` mudo | ✅ |
| PERF-06 | `timings` do servidor dita prefill e decode | `tests/test_providers.py:245,247` — `assert speed.prefill_tps == 70.15`, `timings_source == "server"` | `prompt_per_second` do servidor | ✅ |
| PERF-07 | sem `timings`, prefill fica desconhecido | `tests/test_providers.py:257-258` — `assert speed.prefill_tps is None`, `timings_source == "client"` | `None`, nunca estimado | ✅ |
| PERF-08 | `prompt_eval_s` recebe `prompt_ms/1000` | `tests/test_providers.py:261` — `test_prompt_eval_s_comes_from_prompt_ms` | campo antes nunca escrito | ✅ |
| PERF-09 | prefill ausente exibe `–`, não zero | `tests/test_reports.py:215-216` — `assert "0.00" not in out` e `assert "–" in out` | traço, nunca zero falso | ✅ |
| PERF-10 | mede nas profundidades pedidas | `tests/test_depth_measure.py:71` — `assert [pt.depth_requested for pt in sweep.points] == [0, 8192, 32768]` | um ponto por profundidade | ✅ |
| PERF-11 | `--depths` respeita a lista e a ordem | `tests/test_cli.py:40,46` — `assert args.depths == "0,8192,32768"` / `"0,4096"`; `tests/test_runner_depth_sweep.py:62` — `== [32768, 8192, 0]` | ordem dada preservada | ✅ |
| PERF-12 | profundidade real vem do `prompt_n` | `tests/test_depth_measure.py:84` — `assert pt.depth_actual == 8190` (alvo era 8192) | o que o servidor processou | ✅ |
| PERF-13 | cada ponto grava as métricas do design | `tests/test_depth_measure.py:94-100` — `prefill_tps == 2709.0`, `decode_tps == 83.3`, `ttft_s == 0.42`, `prompt_eval_s == 3.02`, `output_tokens == 128`, `depth_actual == 8190`, `skipped is None` | `DepthMetrics` completo | ✅ |
| PERF-14 | contexto estourado pula só aquela profundidade | `tests/test_depth_measure.py` — `PERF-14: a depth the model cannot hold`; `tests/test_runner_empty_generation.py:60-61` mostra as demais seguindo | pula uma, mede o resto | ✅ |
| PERF-15 | `speed` é a profundidade mais rasa | `tests/test_runner_depth_sweep.py:62,64` — com `depths == [32768, 8192, 0]`, `assert report.speed.tokens_per_sec == 95.1` | a mais rasa, independente da ordem | ✅ |
| PERF-16 | run antigo carrega com lista vazia | `tests/test_history.py:186` — `assert report.depth_results == []` | compat de `from_dict` | ✅ |
| PERF-17 | `diff` compara decode na profundidade 0 | `tests/test_history.py:229` — `assert m["tps"] == 83.3  # decode at depth 0, not the sweep` | histórico intacto | ✅ |

**17/17 ACs com evidência `file:line` e valor asserido igual ao definido na spec.** Nenhuma
lacuna de precisão de spec: todo AC define resultado concreto e o teste mira exatamente ele.

Cobertura das superfícies de saída (PERF-17 AC4) verificada em quatro formatos:
`tests/test_reports.py:269` (Markdown), `:299` (HTML), `:322` (JSON), `:351` (plainui) e
`tests/test_tui.py` (Textual).

---

## Sensor de discriminação

Rodado em `git worktree` isolado sob o scratchpad, com `PYTHONPATH` apontado para o worktree
(origem do import confirmada antes de começar). Nunca `git stash`. Árvore real conferida contra
baseline no fim: **idêntica** (` M CLAUDE.md`, `?? homebench-report.md`, ambos anteriores à feature).

| # | Mutação injetada | Alvo | Resultado |
| --- | --- | --- | --- |
| M1 | TTFT deixa de disparar em `reasoning_content` | `openai_compat.py:145` | **morto** — 2 falhas |
| M2 | `timings_source` fixo em `"client"`, ignora o servidor | `openai_compat.py:176` | **morto** — 1 falha |
| M3 | `depth_actual` reporta o alvo pedido, não `prompt_n` | `depth.py:249` | **morto** — 2 falhas |
| M4 | engole todo `ProviderError`, não só overflow de contexto | `depth.py:237` | **morto** — 3 falhas, incluindo `test_runner_error_isolation.py` (MLC-11) |
| M5b | célula de prefill imprime `0.00` em vez de `–` | `report.py:174` | **morto** — 2 falhas |
| M6 | `speed` vira a profundidade mais funda em vez da mais rasa | `depth.py:264` | **morto** — 2 falhas |

**6 mutações injetadas, 6 mortas, 0 sobreviventes.**

Uma sétima tentativa (`fmt_tps(row.prefill_tps or 0.0)`) sobreviveu e foi **descartada como
mutante equivalente**, não contada como lacuna: `fmt_tps(0.0)` e `fmt_tps(None)` devolvem ambos
`'–'` (verificado diretamente), então a saída é idêntica byte a byte e nenhum teste poderia
distinguir. Substituída pela M5b, que produz saída de fato diferente e foi morta.

---

## Desvios registrados

| # | Desvio | Onde | Julgamento |
| --- | --- | --- | --- |
| 1 | `measure_at_depths` devolve `DepthSweep`, não `List[DepthMetrics]` como no design | marcador em `metrics/depth.py:161` | **Aceito.** `ModelReport.speed` precisa do `SpeedMetrics` completo da profundidade mais rasa, que `DepthMetrics` não carrega. Marcador `SPEC_DEVIATION` presente. |
| 2 | `metrics/depth.py` importa `providers.base` | `depth.py:20` | **Aceito.** AD-005 restringe o pacote `lifecycle/`, não `metrics/`; `metrics/throughput.py:20` já faz o mesmo import. O tokenizer segue injetado como callable. |
| 3 | `cache_n` mora em `GenerationResult`, não em `SpeedMetrics` | `providers/base.py` | **Aceito.** Não é métrica de velocidade e não é serializado no run salvo. |
| 4 | `depth_results` é populado mesmo com `--depths 0` | `runner.py` | **Aceito.** PERF-13 AC5 é incondicional. Consequência documentada: "run sem profundidade" agora significa só run salvo antes da feature. |
| 5 | Aviso guardado passou a ser autodescritivo; prefixo redundante removido do `plainui` | `runner.py:209`, `plainui.py:132` | **Aceito.** Correção de defeito autorizada explicitamente; duas asserções pré-existentes em `test_runner_unload_warning.py` ajustadas ao texto novo — mudança de comportamento deliberada, não asserção enfraquecida. |
| 6 | Rastreabilidade do lote 1 fechada num commit final em vez de por tarefa | `c702f8c` | **Aceito com ressalva.** Sem impacto no código; quebrou a regra de fechar estado junto com a tarefa. Corrigido nos lotes 2 e 3. |

Nenhum teste foi enfraquecido, pulado ou deletado. Contagem subiu monotonicamente 378 → 454.

---

## Critérios de sucesso da spec

| Critério | Situação |
| --- | --- |
| `Ornith-1.5-35B-A3B-Q8` reporta ≈54 tok/s e não `0.00` | **Pendente de teste ao vivo.** Coberto por teste unitário (PERF-01); o número real (54.03 tok/s, TTFT 129 ms) foi medido na mão antes da implementação. |
| `gemma4-e2b` mostra 3 linhas com decode decrescente | **Pendente de teste ao vivo.** Os valores reais (95.1 / 83.3 / 73.0) são os fixtures dos testes. |
| Prefill ≈2 700 tok/s em profundidade 0 | **Pendente de teste ao vivo.** |
| Runs antigos continuam abrindo em `history` | ✅ `tests/test_history.py:186,198-200` |
| Suíte verde sem rede | ✅ 449 passed, 5 skipped (os pulados são os `HOMEBENCH_LIVE`, nunca no CI) |

Os três primeiros exigem o router real e ficam como **passo de aceitação do usuário**, não como
lacuna de implementação: a lógica está coberta por teste determinístico com os valores medidos.
