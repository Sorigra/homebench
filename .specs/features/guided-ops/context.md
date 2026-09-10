# Guided Ops Context

**Gathered:** 2026-09-10
**Spec:** `.specs/features/guided-ops/spec.md`
**Status:** Ready for design

---

## Feature Boundary

Dois superfícies, um produto: um `setup.sh` que pergunta e instala só o homebench, e um
painel TUI de teclado que é o caminho cotidiano depois disso.

O painel é **um programa, várias telas**, como BIOS. Faixa de status sempre visível
(host, up/down, build, residentes). Telas: Planejar, Rodar, Doctor (leitura), Histórico
(lista). Rodar confirma descarga quando AD-002 exige e dispara o leaderboard já existente.

Não instala llama.cpp. Não mexe em container. Não traz GPU ao vivo. Não traz throughput,
`diff` nem `report` para dentro da TUI.

---

## Implementation Decisions

### Formato da tela principal

- Híbrido: faixa de status sempre visível + menus de planejamento.
- Várias telas no mesmo processo, navegação tipo BIOS. Não é tudo numa tela só.
- Não é um wizard de 7 telas em sequência.
- Não é um dashboard só de métricas tipo `amdgpu_top` puro. O “híbrido” é o layout, não VRAM.

### Alcance do instalador

- `setup.sh` na raiz do repo.
- Cria `.venv`, `pip install -e .` (sem `[dev]`), grava `config.json`, tenta lançador
  em `~/.local/bin`, roda uma checagem de leitura do router.
- Defaults: `http://127.0.0.1:8080`, `~/llm-server/llama/api-key.txt`, `/home/eskudo/ai-models`.
- `--defaults` para não-interativo / testes.
- Router down não desfaz a instalação e não tenta levantar Docker.

### Recorte do MVP do painel

- Travado em 2026-09-10 pelo operador: Planejar + Rodar + Doctor (leitura) + Histórico (lista).
- Throughput permanece na CLI neste corte.
- GPU ao vivo adiado.

### Comando sem argumentos

- `homebench` com argv vazio + TTY (stdin e stdout) → painel.
- Qualquer argumento → CLI atual (`homebench run ...` continua igual).
- Argv vazio sem TTY → auto-run `plainui` (não quebrar script/CI).

### Agent's Discretion

- Layout Textual concreto (widgets, teclas além de `q`/`r`/Enter), desde que a faixa de
  status permaneça visível nas telas de planejamento, Doctor e Histórico.
- Schema exato de `config.json` (nomes dos campos), desde que cubra host, api_key_file,
  model_dir e last_plan.
- Como o setup detecta Python 3.9+ (`python3` vs `python3.12`).
- Texto das mensagens, em português, curto.
- Profundidades no Planejar: os três valores padrão atuais (`0`, `8192`, `32768`) como
  toggles independentes. Sem campo livre de profundidade neste corte.
- Tipo de teste: três opções mutuamente exclusivas — só velocidade, só qualidade, os dois.

### Declined / Undiscussed Gray Areas → Assumptions

Nenhuma área ficou em aberto. Item 3 foi aceito em 2026-09-10: BIOS multi-tela;
throughput e GPU fora do MVP.

---

## Specific References

- “setup.sh que pergunta o necessário e instala”
- “depois de instalado é só chamar o executável”
- TUI “como se fosse uma BIOS de planejamento” ou “como o amdgpu_top”
- Escolher modelos, tamanho de contexto, tipos de teste, status do llama.cpp
- `docs/USO.md` está confuso; o caminho primário deve ser setup + painel
- Visão original em `docs/contexto-llm-benchmark.md` (fluxo guiado), ainda não construída
- AD-001, AD-002, AD-005, AD-007 continuam valendo

---

## Deferred Ideas

- Painel GPU AMD ao vivo (já fora de `model-lifecycle`)
- `diff` / `report` dentro da TUI
- Throughput no painel
- Wizard sequencial de 7 telas do doc de contexto (boas-vindas → GPU → modelo → params → perfis)
- `homebench setup` em Python no lugar do `setup.sh` (o shell é o pedido)
- Campo livre de profundidade além dos três toggles padrão
