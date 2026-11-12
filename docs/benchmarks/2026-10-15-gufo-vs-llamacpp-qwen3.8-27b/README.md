# gufo vs llama.cpp — Qwen3.8 27B Q4 no Strix Halo (15/10/2026)

Comparação de velocidade, vazão e qualidade entre o [gufo](https://github.com/gufo-org/gufo)
(engine específica para Strix Halo) e o router llama.cpp ROCm de produção, usando o mesmo
GGUF. Cada engine rodou sozinha na máquina (os outros containers parados).

## Ambiente

- AMD Strix Halo (gfx1151), ~121 GiB de memória unificada, Ubuntu 26.04, kernel 7.0.
- Modelo: `unsloth/Qwen3.8-27B-GGUF` → `Qwen3.8-27B-UD-Q4_K_XL.gguf`
  (sha256 `3f227079…c8b01e`, idêntico à revisão `4ca72078` fixada pelo gufo).
- **llama.cpp:** imagem `kyuz0/amd-strix-halo-toolboxes:rocm-10.0`, build `b11590`,
  HIP 7.15 (a tag "10.0" não é a versão do ROCm). Preset: f16 KV, MTP
  (`spec-type = draft-mtp`, `spec-draft-n-max = 3`), `reasoning-effort = medium`,
  `reasoning-budget = 1536`, temp 1.0 / top-p 0.95 / top-k 20.
- **gufo:** v0.15.1 (`f711612`), imagem `gufo-runtime` fixada por digest, ROCm 7.2.3.
  DFlash2 com `z-lab/Qwen3.8-27B-DFlash2-GGUF` → `Qwen3.8-27B-DFlash2-Q4_K_M.gguf`
  (revisão `2d9571f8`, ~1,1 GB). Mesma amostragem e `reasoning-effort medium`.
  Compose em [`gufo-docker-compose.yml`](gufo-docker-compose.yml).

## Velocidade, 1 usuário (`homebench run --no-quality`, 256 tokens, melhor de 3)

| Profundidade | gufo DFlash2 pp | llama MTP pp | gufo DFlash2 tg | llama MTP tg | gufo sem draft tg |
| --- | --- | --- | --- | --- | --- |
| curta | 157 | 82 | **26,6** | 24,0 | 12,2 |
| ~8k | **501** | 328 | **24,9** | 22,6 | 11,9 |
| ~30k | **496** | 283 | **20,7** | 19,0 | 11,1 |

- O provider `openai` estima a profundidade, por isso o gufo mediu 6.894 / 27.374 tokens e o
  llama 8.202 / 32.778. As taxas por token são comparáveis; o TTFT absoluto, não.
- `llama-bench` sem draft: pp512 378, pp2048 353, tg128 **12,0** tok/s. Sem draft as duas engines
  empatam na geração; o ganho de geração do gufo vem do DFlash2.

## Vazão (`homebench throughput`, 256 tokens/req)

| Usuários | llama 1 slot | llama 4 slots | gufo 4 sessões |
| --- | --- | --- | --- |
| 1 | 21,7 | 21,7 | **29,1** |
| 2 | 21,9 | 28,7 | **39,4** |
| 4 | 22,1 | 51,8 | 52,4 |
| 8 | – | 52,9 | 52,5 |

Com 4+ usuários as duas batem no mesmo teto (~52 tok/s, limite de banda de memória).
A vantagem do gufo fica com 1–2 usuários (~35%) e no prefill (~1,5–1,8×).

## Qualidade (`homebench run --full --no-speed`, 31 tarefas determinísticas)

- llama: **31/31**, 3.235 tokens gerados. gufo: **31/31**, 3.242 tokens.
- As tarefas embutidas têm limites de 60–300 tokens; com raciocínio ligado, o modelo esgota o
  limite pensando e devolve resposta vazia (primeira tentativa no llama: 21/31). Os resultados
  acima usam [`hb_bigtokens.py`](hb_bigtokens.py), que sobe todos os limites para 2048.
- A bateria é fácil para um 27B: serve como teste de sanidade (o gufo não degrada a saída),
  não para distinguir modelos.

## Comparação com os números publicados pelo gufo

Os [benchmarks do gufo](https://github.com/gufo-org/gufo/blob/main/docs/models/qwen3.8-27b/BENCHMARKS.md)
batem com os nossos nas linhas equivalentes (tg sem draft 12,37; DFlash2 texto misto, contexto 0: 26,13).
Os ~70 tok/s divulgados são da linha "repetitive" (texto previsível, greedy, raciocínio desligado,
até 128 tokens), não de uso geral.

## Mudanças que resultaram dos testes

- Preset do `qwen3.8-27b-unsloth` em produção: `parallel 1 → 4` e `ctx-size 131072 → 524288`
  (no llama.cpp o `ctx-size` é o total dividido entre os slots; com isso cada slot tem 128k).
  KV estimado ~68 KiB/token (17 camadas de atenção × 4 cabeças KV × 256 × K+V × f16),
  ~8,5 GiB por slot de 128k. Uso de memória da máquina subiu de ~52 para ~65 GB.
- O gufo ficou instalado mas parado (`127.0.0.1:8090`, sem Traefik).

## Próximo passo considerado: Qwen3.8-Flash-Next no gufo

Os números publicados para o Flash-Next (MoE, ~125B/180B totais, ~6B ativos) mostram o gufo bem à
frente do llama.cpp, sobretudo em contexto longo (tg AR 27 vs 8 tok/s a 128k; pp ~1.500 vs 145).
Pontos em aberto antes de testar:

- Pico de ~89 GiB com 1 sessão de ~133k: não coexiste com a produção atual.
- Download de ~104 GiB (UD-Q4_K_XL em 4 partes + MTP Q8, revisão `38bb39ee`).
- Inteligência: o Artificial Analysis dá 40 ao Flash-Next contra 26 ao 27B com raciocínio *Low*,
  mas o 27B com raciocínio completo é citado com 52. Licença `qwen-community-1.0` e status de
  prévia experimental. Para decidir, montar um pacote de tarefas com casos reais de trabalho.

## Arquivos

`raw/` contém os JSON e Markdown originais de cada execução (`gufo-*`, `llama-*`).
