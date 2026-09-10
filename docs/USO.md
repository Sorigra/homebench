# Como usar o homebench (fork Strix Halo)

Guia prático para rodar o `homebench` **neste ambiente**: mini PC AMD Strix Halo, com o
llama.cpp em **modo router** dentro do Docker (`~/llm-server/llama/docker-compose.yml`).

- **`llama-vulkan`** → `http://127.0.0.1:8080`
- **`llama-rocm`** → `http://127.0.0.1:8081`
- Modelos no host em `/home/ai-models`, montados como `/models` no container.
- Chave da API em `~/llm-server/llama/api-key.txt`.

> O foco desta fork é **performance bruta** (tok/s, TTFT, memória). O teste de qualidade
> é secundário — na maioria das vezes você vai querer `--no-quality`.

---

## 1. Instalação

Já está instalado no repo (`.venv/`). Para recriar do zero:

```bash
cd ~/homebench
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/homebench --help
```

O comando é `.venv/bin/homebench` (ou `homebench` se o `.venv` estiver ativado com
`source .venv/bin/activate`).

---

## 2. Apontar para o router

O `homebench` fala com o router por HTTP. Diga qual host e passe a chave:

```bash
export LLAMACPP_HOST=http://127.0.0.1:8080          # vulkan
export LLAMACPP_API_KEY="$(cat ~/llm-server/llama/api-key.txt)"
export HOMEBENCH_MODEL_DIR=/home/ai-models          # preenche a coluna Memory
```

As duas primeiras são obrigatórias. A terceira diz onde os modelos ficam **no host**: sem ela a
coluna `Memory` sai em branco (ver §5b). Para não redigitar toda vez:

```bash
echo 'export HOMEBENCH_MODEL_DIR=/home/ai-models' >> ~/.bashrc
```

Ou por comando, sem exportar nada:

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 ...
```

O `homebench` descobre sozinho que é um router (`GET /props` → `role: router`) e liga o
gerenciamento de modelo. Contra um `llama-server` comum ele se comporta como antes.

---

## 2b. Apontar para um servidor vLLM

O vLLM expõe uma API compatível com OpenAI. Por padrão o `homebench` procura o servidor em
`http://localhost:8000`; para outro endereço, use `--host` ou `VLLM_HOST`:

```bash
export VLLM_HOST=http://127.0.0.1:8000
# Somente se o servidor foi iniciado com `vllm serve ... --api-key`:
export VLLM_API_KEY='sua-chave'
```

Primeiro confirme que o servidor responde e veja o id exato publicado por `/v1/models`:

```bash
.venv/bin/homebench list --provider vllm --host http://127.0.0.1:8000
```

Depois rode o benchmark de latência e velocidade. Como o foco desta fork é performance bruta,
este exemplo desliga qualidade e mede somente contexto zero:

```bash
.venv/bin/homebench run --provider vllm --host http://127.0.0.1:8000 \
  --no-quality --depths 0 -m ID_EXATO_DO_MODELO
```

Para medir o ganho de batching/concorrência do vLLM:

```bash
.venv/bin/homebench throughput --provider vllm --host http://127.0.0.1:8000 \
  -m ID_EXATO_DO_MODELO --concurrency 1,2,4,8
```

O benchmark oficial do vLLM é uma segunda referência útil. Quando o servidor roda no container
`vllm-rocm`, este comando fixa 8192 tokens de entrada, 128 de saída e concorrência 1:

```bash
docker exec -it vllm-rocm vllm bench serve \
  --backend vllm \
  --host 127.0.0.1 \
  --port 8000 \
  --dataset-name random \
  --input-len 8192 \
  --output-len 128 \
  --num-prompts 1 \
  --max-concurrency 1 \
  --ignore-eos
```

`--ignore-eos` impede encerramento antecipado e mantém a quantidade de tokens de saída comparável
entre runs. Não remova essa opção em workloads controlados.

Se `VLLM_HOST` já estiver exportada, `--host` pode ser omitido. O `homebench` não inicia,
carrega nem encerra o vLLM: o modelo precisa estar servido antes do teste. A API OpenAI do vLLM
não inclui timings no stream como o llama.cpp, mas o `homebench` lê os deltas server-side de
`/metrics` durante as sondagens de velocidade. Com exatamente uma requisição no intervalo,
`Prefill tok/s` usa tokens KV realmente computados e `Decode tok/s` usa o tempo de decode do
servidor. Se `/metrics` não estiver disponível ou outra requisição concorrer no intervalo, o
prefill fica em branco e decode/TTFT continuam sendo medidos pelo cliente. `Memory` pode ficar em
branco porque a API não informa o uso residente do modelo.

---

## 3. Ver o que está carregado

```bash
.venv/bin/homebench models --provider llamacpp --host http://127.0.0.1:8080
```

Lista os 17 modelos do host, o estado de cada um (`loaded` / `loading` / `unloaded`) e,
para os residentes, o argv efetivo com que o router subiu. Substitui montar `curl` na mão.

```bash
.venv/bin/homebench doctor
```

Inclui uma checagem de alcançabilidade e autenticação do router (cita o `build_info` e
quantos modelos estão residentes).

---

## 4. Rodar um benchmark de performance

**O básico** — 3 modelos menores, só velocidade e memória:

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 --no-quality
```

**Modelos específicos:**

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 --no-quality \
  -m qwen35-4b,gemma4-e4b,qwen35-9b
```

**Todos:**

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 --no-quality --all
```

### O que acontece com o ciclo de vida

Antes de medir cada modelo, o `homebench`:

1. Garante que **só aquele modelo** está residente (descarrega os outros — é o `--models-max 3`
   do router que torna isso necessário: um segundo modelo disputando VRAM contamina o tok/s).
2. Carrega o modelo se preciso e espera ficar `loaded` (até 300 s).
3. Grava, junto com o resultado, o argv efetivo com que ele carregou.

**Confirmação:** se houver um modelo residente que **não** faz parte deste run (por exemplo
alguém usando o Open WebUI), o `homebench` mostra quais serão descarregados e **pergunta antes**.
Para pular a pergunta (uso automático / script):

```bash
.venv/bin/homebench run ... --force-unload
```

Num terminal não interativo sem `--force-unload`, ele **aborta** com uma mensagem em vez de
descarregar por conta própria.

### `model limit reached`: o slot que o router demora a liberar

O router aceita no máximo `--models-max` instâncias residentes (3 neste deployment) e, ao
atingir o teto, ele **recusa** a carga em vez de despejar o modelo mais antigo:

```
Router rejected /models/load for 'x': model limit reached, try again later
```

O `POST /models/unload` responde **antes** de o slot ser efetivamente liberado, então descarregar
e carregar em seguida corria contra o router e podia bater nesse erro mesmo tendo acabado de
liberar espaço. Depois de descarregar, o `homebench` agora espera o `GET /props` →
`max_instances` bater com a contagem de `loaded` do `GET /v1/models` antes de carregar (até 60 s).

A causa mais comum de encostar no teto era ter **seções de preset duplicadas** — uma seção de
benchmark apontando para o mesmo `.gguf` de uma seção de produção cria um **segundo id**, que
ocupa um slot e uma cópia inteira da memória. Uma seção por `.gguf`, com o nome igual ao id que o
`--models-dir` já descobre, evita as duas coisas.

### O router pode ignorar `load-params.json` — e agora ele avisa

`POST /models/load` aceita um campo `extra_args`, e é por ele que o
`$HOMEBENCH_HOME/load-params.json` tenta testar parâmetros de carga sem mexer no
arquivo de presets. **No build `b10878` o router aceita esse campo, responde
`{"success": true}` e carrega o modelo só com o preset**, sem aplicar nada:

```
$ curl -X POST .../models/load -d '{"model":"qwen3.8-27b-unsloth",
    "extra_args":["--cache-type-k","f16","--flash-attn","off"]}'
{"success":true}
$ # ... e o argv resolvido continua:
--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on
```

Sem verificação isso é pior que um erro: o benchmark roda, grava um número e o
rotula com parâmetros que nunca existiram. O `homebench` agora compara o que
pediu com o argv que o router reporta depois de carregar e avisa:

```
warning: the router ignored these load parameters for qwen3.8-27b-unsloth:
-ctk f16, -fa off — it loaded from its own preset instead, so this result does
NOT measure them.
```

Para testar parâmetros de carga contra um router assim, edite o
`presets-rocm.ini` e reinicie o container — o preset só é lido no boot.

---

## 5. Profundidade de contexto (`--depths`)

Por padrão o `homebench` mede cada modelo em **três profundidades de contexto**: `0`, `8192` e
`32768` tokens de prompt. Um modelo real perde velocidade conforme o contexto cresce — no
`gemma4-e2b` medido ao vivo, o decode cai de ~95 para ~73 tok/s (23%) e o prefill de ~2 700 para
~1 800 tok/s (33%) entre profundidade 0 e 32k. Medir só em contexto zero, como o `homebench`
fazia antes desta feature, escondia essa degradação.

O leaderboard agora mostra **uma linha por (modelo, profundidade)**, com colunas separadas de
`Prefill tok/s` e `Decode tok/s` — não são o mesmo regime e ficam ordens de grandeza distantes
(milhares vs dezenas), então uma coluna só de "tok/s" escondia qual dos dois estava sendo medido.

**Isso custa tempo.** A varredura roda três medições por modelo em vez de uma; um prefill de 32k
sozinho leva **~18 s** num modelo pequeno como o `gemma4-e2b`, e bem mais num modelo grande (o
prefill de 32k de um 35B pode passar de um minuto). Para o benchmark rápido de sempre, sem a
varredura:

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 --no-quality --depths 0
```

`--depths 0` reproduz exatamente o comportamento de antes desta feature: uma medição por modelo,
em contexto ~zero. Também aceita uma lista customizada, na ordem dada:

```bash
.venv/bin/homebench run ... --depths 0,4096,16384
```

Um valor que excede a janela de contexto do modelo não derruba o run inteiro: aquela profundidade
aparece pulada, com o motivo, e as demais seguem normalmente.

### `--ctx-size` **não** é o contexto de uma requisição

O `llama.cpp` reparte o cache KV entre os slots de `--parallel`. O que uma requisição pode usar é
`ctx-size / parallel`, e a mensagem de erro do servidor só cita o resultado da divisão, nunca a
divisão:

| preset | `ctx-size` | `parallel` | contexto por requisição |
| --- | --- | --- | --- |
| `foundation-sec-8b-reasoning-q8_0` | 32768 | 2 | **16384** |
| `gemma4-e2b` | 16384 | 4 | **4096** |
| `qwen3.8-27b-unsloth-mtp` | 131072 | 1 | **131072** |

O `homebench` **pula a profundidade antes de enviar a requisição**, dizendo de onde veio o limite:

```
skipped: needs ~8292 tokens, server context is 4096 (--ctx-size 16384 / --parallel 4)
```

Sem isso a profundidade só falhava depois do round trip, e o motivo chegava como um corpo de HTTP
400 de três linhas ocupando a tabela inteira.

### De onde vem o limite: o servidor, não o argv

O argv é um **teto pedido**, não o contexto servido. Além de dividir por `--parallel`, o
`llama.cpp` ainda **corta o `ctx-size` no contexto treinado do modelo, em silêncio**: um preset
pedindo `ctx-size = 133120` num `gemma4-e2b` (treinado a 131072) serve 131072 e não avisa nada.
Quem lê só as flags de lançamento fica com um número que o servidor nunca honrou.

Por isso o limite vem de `GET /props?model=<id>`, que devolve o `n_ctx` da instância carregada —
já dividido pelos slots e já cortado no contexto treinado. Confirmado ao vivo:

| modelo | `--ctx-size` | `--parallel` | `n_ctx` servido |
| --- | --- | --- | --- |
| `gemma4-e2b` | 16384 | 4 | **4096** |
| `foundation-sec-8b-reasoning-q8_0` | 32768 | 2 | **16384** |
| `qwen3.8-27b-unsloth-mtp` | 131072 | 1 | **131072** |

O argv continua como reserva para backends que não sabem responder `/props`. Quando nenhum dos
dois sabe, o limite fica desconhecido e a varredura roda igual a antes — o servidor decide, não o
`homebench`.

**Para medir a 128k** o preset precisa de `parallel = 1`, e a profundidade tem de caber junto com
a resposta: prompt e resposta dividem a mesma janela, então uma janela de 131072 recusa uma
profundidade de 131072 exatamente pelos ~100 tokens que a sonda gera. Como o corte no contexto
treinado impede simplesmente pedir mais, a profundidade útil da classe 128k é **130048**:

```bash
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8081 --no-quality \
  --depths 0,8192,32768,130048 -m bench-gemma4-e2b-128k
```

### Timeout nas profundidades grandes

O `--timeout` (padrão 300 s) é o piso, não o teto. Um prefill de 128k leva minutos — o
`qwen3.8-27b` mediu 141 s só para 32k — e um teto fixo transformaria isso num `skipped` por
timeout indistinguível de um backend travado. A partir de agora a varredura **projeta** o timeout
de cada profundidade a partir do prefill que ela mesma acabou de medir na profundidade anterior,
com 3× de margem:

| prefill medido | timeout a 131072 |
| --- | --- |
| 1121 tok/s (`foundation-sec-8b` q8_0) | ~651 s |
| 233 tok/s (`qwen3.8-27b` Q4_K_M) | ~1988 s |

Na profundidade mais rasa, sem nada medido ainda, vale o `--timeout` puro.

---

## 5b. A coluna `Memory`

`Memory` é o **tamanho do modelo residente**; `Peak` é o crescimento de RSS do processo do
servidor durante o run.

Aqui o `Peak` sozinho **mente para baixo**: com `--n-gpu-layers 999` os pesos vão para a memória
da GPU e nunca entram no resident set do `llama-server` — o `Ornith-1.5-35B-A3B-Q8`, que ocupa
37,8 GB, aparecia com 2,3 GB de Peak e `Memory` em branco.

O `homebench` agora lê o argv que o router resolveu (`GET /v1/models` → `status.args`), pega o
caminho do `--model` e mede o GGUF. Como o servidor roda em container, o caminho que ele reporta
(`/models/...`) não existe deste lado do mount; diga onde é no host:

```bash
export HOMEBENCH_MODEL_DIR=/home/ai-models
```

Sem essa variável a coluna fica **em branco** — nunca um número inventado. Se o modelo for um
GGUF dividido (`-00001-of-00003.gguf`), o total soma todos os pedaços.

---

## 6. Testar parâmetros de carga (`-ngl`, contexto, flash attention)

Crie `~/.homebench/load-params.json` com os flags extras por modelo:

```json
{
  "qwen35-4b": ["-ngl", "99", "-fa"],
  "gemma4-e4b": ["-ngl", "20"]
}
```

Na próxima carga daquele modelo o `homebench` manda esses flags em `extra_args` no
`POST /models/load`. Se o router recusar um flag, a mensagem de erro dele aparece sem
reinterpretação.

Dois runs do mesmo modelo com `-ngl` diferente ficam **distinguíveis no histórico** — cada run
salvo registra o argv efetivo. Use `--label` para marcar:

```bash
.venv/bin/homebench run ... -m qwen35-4b --label "ngl-99"
# edite o load-params.json
.venv/bin/homebench run ... -m qwen35-4b --label "ngl-20"
.venv/bin/homebench diff
```

> Precedência dos parâmetros: flag explícita > `load-params.json` > preset do servidor >
> heurística > default do llama.cpp. Hoje o router tem preset para tudo em `/home/ai-models`,
> então sem o `load-params.json` ele usa o preset.

---

## 7. Comparar Vulkan vs ROCm

Os dois backends rodam sobre a mesma GPU. Rode o mesmo modelo nos dois hosts e compare:

```bash
mkdir -p benchmark-results

.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 \
  --no-quality -m qwen35-4b --label "vulkan" \
  --json benchmark-results/vulkan.json

.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8081 \
  --no-quality -m qwen2.5-7b-instruct-q4_k_m-rocm --label "rocm" \
  --json benchmark-results/rocm.json

.venv/bin/homebench diff
```

> Atenção: os ids de modelo diferem entre os hosts (o ROCm tem sufixo `-rocm` e só 2 modelos).
> A comparação só é justa se os **dois hosts rodarem o mesmo build** do llama.cpp — hoje ambos
> estão em `b10664`, então está ok. Se divergirem, você está medindo o build tanto quanto o
> backend.

---

## 8. Histórico

Todo run é salvo automaticamente em `~/.homebench/runs/`.

```bash
.venv/bin/homebench history          # lista os runs (mais novo primeiro)
.venv/bin/homebench diff             # penúltimo → último
.venv/bin/homebench diff 3 1         # run #3 (base) → run #1
.venv/bin/homebench report latest --html run.html   # renderiza um run salvo
```

---

## 9. Limitações conhecidas neste ambiente

- **Corrigido:** modelos de raciocínio (ex. `qwen35-4b`) devolvem o texto em
  `reasoning_content`. Antes desta feature o `homebench` não lia esse campo, e o tok/s não saía
  "subestimado" — saía **zerado**: `Ornith-1.5-35B-A3B-Q8` reportava `0.00 tok/s` com TTFT de
  129 ms, um resultado com cara de válido mas completamente falso. Um `reasoning_content` não
  vazio agora conta para TTFT, tempo de decode e contagem de tokens, e o mesmo modelo mede
  ≈54 tok/s reais.
- **Erro no meio do stream.** O `llama-server` pode devolver `200` e mandar
  `data: {"error": ...}` dentro do stream — por exemplo quando o prompt estoura a janela de
  contexto. Antes isso passava despercebido e virava mais um `0.00 tok/s` com cara de resultado
  válido (foi o que aconteceu com o `foundation-sec-8b-q4_k_m` em 32768). Agora vira erro de
  verdade: se a mensagem falar de contexto, aquela profundidade aparece **pulada com o motivo**
  e as outras seguem.
- **`gpt-oss-120b` mede o modelo errado.** Não existe bloco `[gpt-oss-120b]` no
  `presets.ini` — só `[gpt-oss-120b-eagle3]`. Esse id foi inventado pelo router varrendo o
  diretório (`source = models_dir`), e ele pegou o primeiro `.gguf` da pasta em ordem
  alfabética: o `eagle3-gpt-oss-120b-Q8_0.gguf`, de **849 MB**, que é o modelo de rascunho — não
  o `gpt-oss-120b-MXFP4.gguf` de 63 GB. Benchmarcar `gpt-oss-120b` mede o draft. Use
  **`gpt-oss-120b-eagle3`**, que tem preset explícito e está correto (MXFP4 como `--model`, o
  eagle3 como `spec-draft-model`). Corrigir de vez pede um bloco `[gpt-oss-120b]` no
  `presets.ini` — e isso só entra em vigor **reiniciando o container**, o que é decisão sua e
  fora do que o `homebench` faz.
- **`POST /models/unload` é assíncrono** no build `b10664`: retorna antes de o modelo sumir de
  `GET /v1/models`. O `homebench` se auto-corrige (replaneja no próximo modelo), mas se você
  inspecionar na mão logo após, pode ver o modelo ainda `loaded` por alguns segundos.
- **Nunca** mexa nos containers (`docker restart` etc.) — eles servem o Open WebUI e o Traefik
  em produção. Todo o ciclo de vida do `homebench` é por HTTP, sem tocar no container.

---

## 10. Teste ao vivo (para desenvolvimento)

Há um teste de integração que roda o ciclo completo contra os dois routers reais. É **desligado
por padrão** (nunca roda no CI):

```bash
HOMEBENCH_LIVE=1 .venv/bin/python -m pytest -q tests/test_live_router.py
```

Ele carrega o menor modelo, gera um texto curto, descarrega e **restaura o estado inicial** dos
routers ao terminar (mesmo se falhar). Variáveis opcionais: `HOMEBENCH_LIVE_MODEL` (fixar o
modelo), `HOMEBENCH_LIVE_MODEL_DIR` (default `/home/ai-models`).
