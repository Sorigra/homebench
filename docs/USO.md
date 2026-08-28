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

1. Garante que **só aquele modelo** está residente (descarrega os outros — é o `--models-max 2`
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
.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8080 \
  --no-quality -m qwen35-4b --label "vulkan" --json vulkan.json

.venv/bin/homebench run --provider llamacpp --host http://127.0.0.1:8081 \
  --no-quality -m qwen2.5-7b-instruct-q4_k_m-rocm --label "rocm" --json rocm.json

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
