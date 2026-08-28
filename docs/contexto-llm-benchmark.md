# Contexto do projeto: Ferramenta de benchmark de performance para LLMs locais

## Objetivo

Customizar o repositório `homebench` (fork já criado no GitHub, clonado localmente) para virar
uma ferramenta de **teste de performance bruta** de modelos LLM rodando localmente via
**llama.cpp**, numa mini PC Ubuntu com GPU AMD (ROCm) e suporte a CUDA também configurado.

O foco é **performance**, não qualidade das respostas (o homebench já tem um sistema de qualidade
próprio com 31 tarefas, mas isso é secundário aqui — pode ficar desligado por padrão com
`--no-quality`).

## Ambiente

- SO: Ubuntu (servidor/mini PC, sem interface gráfica)
- Motor de inferência: `llama.cpp` compilado com suporte a CUDA e ROCm, já funcionando
- GPU: AMD, monitorada hoje via `radeontop` manualmente em outra aba do terminal
- O usuário **não é desenvolvedor** — vai operar via Claude Code para implementar e ajustar o código
- No futuro, o mesmo motor de testes será exposto também via uma interface web (HTML/backend), então
  a lógica de negócio não pode ficar acoplada à TUI

## Por que o homebench como base

Pesquisamos várias alternativas (llama-bench, llmBench, LM-Studio-Bench, lm-evaluation-harness,
LiveBench, etc.). O homebench foi escolhido porque:

- Já é 100% Python, código modular (`providers/`, `quality/`, `metrics/`, `runner.py`, `report.py`,
  `tui/`, `plainui.py`)
- Já fala o protocolo OpenAI-compatible, então funciona com llama.cpp (`llama-server`) e continuaria
  funcionando se no futuro o usuário trocar para Ollama ou vLLM
- Já mede tok/s, TTFT, memória, e tem um modo `throughput` para concorrência
- Já tem TUI pronta (provavelmente Rich/Textual) e um modo `--no-tui` para uso não interativo (útil
  para a futura API web)
- Licença MIT — fork livre para modificar

### Limitação importante do homebench original (o que falta construir)

O homebench **não gerencia o ciclo de vida do modelo**. Ele assume que o `llama-server` já está de
pé com o modelo carregado, e só bate no endpoint. Ele não:

- Verifica se já existe um modelo carregado na GPU (o que "sujaria" a métrica se for o modelo errado)
- Descarrega um modelo antes de subir outro
- Sobe o `llama-server` com os parâmetros de carregamento (ex: `-ngl`, `-c`, `-fa`, tipo de
  quantização, etc.)
- Sugere parâmetros recomendados por modelo, editáveis pelo usuário antes de carregar

Essa é a principal peça a ser desenvolvida em cima do fork.

## Fluxo desejado da ferramenta (visão de produto)

1. **Tela inicial** ("Bem-vindo ao programa de teste de performance")
2. **Checagem de estado da GPU**: verifica se já existe um modelo carregado (processo do
   `llama-server` rodando / VRAM ocupada). Se houver, oferece descarregar antes de prosseguir —
   para garantir que o teste não meça um modelo errado competindo por recursos.
3. **Seleção de modelo**: lista os modelos GGUF disponíveis localmente (ex: escaneando uma pasta de
   modelos). *Fora de escopo por enquanto*: download de modelo direto pela ferramenta — só
   selecionar entre os já baixados.
4. **Parâmetros de carregamento do llama.cpp**: a ferramenta sugere parâmetros recomendados para
   aquele modelo (ex: `-ngl`, contexto, flash attention, tipo de KV cache), mas permite edição manual
   antes de efetivamente subir o `llama-server` com esses parâmetros.
5. **Seleção de perfis de teste**: escolher quais testes/perfis rodar (tamanhos de prompt diferentes,
   profundidade de contexto, etc.) — não precisa rodar tudo sempre.
6. **Execução com TUI ao vivo**: mostra o teste rodando, % de progresso, modelo atual, consumo de
   memória e de GPU em tempo real — substituindo a necessidade de ter o `radeontop` aberto numa aba
   separada.
7. **Resultado salvo em arquivo** (JSON, como o homebench já faz em `~/.homebench/runs`) — **sem
   necessidade de banco de dados**, mantendo simples.

## Decisões de arquitetura já tomadas

- **Camada de motor de teste separada da interface**: a lógica de benchmark deve ser reutilizável,
  chamável tanto pela TUI (linha de comando) quanto, no futuro, por uma API web. Não colocar lógica de
  negócio dentro do código de renderização da TUI.
- **Comunicação com o modelo via HTTP, protocolo OpenAI-compatible** (não via bindings Python do
  llama-cpp-python direto). Motivo: manter a ferramenta agnóstica de backend (funciona com llama.cpp,
  Ollama, vLLM no futuro), e o overhead de rede localmente é desprezível perto do tempo de geração.
  Essa já é a abordagem do homebench.
- **Gerenciamento do ciclo de vida do modelo (subir/descer o `llama-server` com os parâmetros
  corretos) precisa ser construído como um módulo novo**, hoje inexistente no homebench.
- **Sem banco de dados** — resultados em arquivo (JSON/Markdown), seguindo o padrão que o homebench
  já usa.
- **Monitoramento de GPU AMD**: hoje feito manualmente via `radeontop`; a ferramenta deve
  internalizar isso na própria TUI (avaliar se dá para ler as mesmas fontes que o `radeontop` usa,
  tipo sysfs do amdgpu, ou invocar/parsear o `radeontop` em modo batch).

## O que já existe no homebench (não precisa reinventar)

- Providers plugáveis (`providers/`), incluindo um `llamacpp` já compatível com `llama-server`
- Métricas de tok/s, TTFT, memória (via endpoints nativos quando existem, ou client-side)
- Comando `throughput` para medir taxa agregada sob concorrência (1, 2, 4, 8 requisições simultâneas)
- Exportação em JSON e Markdown, histórico de runs (`homebench history`, `homebench diff`)
- TUI já funcional (`tui/` e `plainui.py` para modo não interativo)
- Sistema de qualidade (pode ficar desligado com `--no-quality`, já que o foco agora é performance)

## O que precisa ser construído/adaptado

1. Módulo de **gerenciamento de modelo**: detectar modelo carregado na GPU, descarregar se
   necessário, subir `llama-server` com parâmetros escolhidos/editados pelo usuário
2. Base de **parâmetros recomendados por modelo** (pode começar simples, hardcoded ou heurística por
   tamanho/quantização do GGUF, refinável depois)
3. Tela/fluxo de **seleção de perfis de teste** (tamanhos de prompt e profundidade configuráveis)
4. **Painel de GPU AMD em tempo real** dentro da própria TUI (substituindo o `radeontop` manual)
5. Adaptar o fluxo de entrada (`homebench` hoje é mais "aponte e rode"; o fluxo novo é mais guiado,
   em etapas — tela de boas-vindas → seleção de modelo → parâmetros → perfis → execução)

## Fora de escopo por agora

- Download de modelos direto pela ferramenta
- Banco de dados
- Testes de qualidade (já existem no homebench, mas não são o foco)
- Interface web em si (só é preciso já pensar a arquitetura para não travar isso depois)

## Pontos em aberto (decidir durante o desenvolvimento)

- Melhor forma de ler VRAM/uso de GPU AMD via ROCm/amdgpu sem depender de rodar `radeontop` como
  subprocesso (mas usar o `radeontop` em modo batch como fallback é aceitável no início)
- Formato exato do arquivo de parâmetros recomendados por modelo (JSON? heurística automática a
  partir de metadados do GGUF?)
- Se o descarregamento de modelo deve ser automático ou pedir confirmação ao usuário
