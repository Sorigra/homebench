# Triagem SIEM com Modelos Locais

Este documento resume os testes realizados em 10 de setembro de 2026 no AMD Strix Halo e mostra como consumir os modelos pelo router ROCm do `llama.cpp`.

## Ambiente e configuração

- Endpoint OpenAI-compatible: `http://127.0.0.1:8080/v1`
- Modelos no host: `/home/eskudo/ai-models`
- Backend ativo: `llama.cpp` ROCm, build `b10878-4850c7727`
- Triagem: `gemma4-e2b`, quatro slots de 32.768 tokens, MTP externo com `n-max=4`
- Investigação: `qwen3.8-27b-unsloth`, um slot de 131.072 tokens
- Qwen: `Qwen3.8-27B-UD-Q4_K_XL.gguf`, KV `f16`, MTP interno, raciocínio médio

O `UD-Q4_K_XL` é a quantização 4-bit recomendada pela [Unsloth](https://unsloth.ai/docs/models/qwen3.8). O arquivo `Q4_K_M` anterior foi preservado para rollback. Foundation-Sec e Ornith continuam disponíveis sob demanda, mas não carregam no boot.

## Resultados dos testes SIEM

Foram usados cinco cenários: PowerShell/LOLBIN, password spray, desativação do CloudTrail, scanner autorizado e comprometimento de identidade com MFA fatigue. A pontuação máxima era 25.

| Modelo | Pontuação | JSON válido | Tempo médio | TTFT médio | Decode |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gemma4-e2b` sem MTP | 22/25 | 5/5 | 2,41 s | 0,124 s | 87,3 tok/s |
| `gemma4-e2b` MTP `n-max=4` | 22/25 | 5/5 | 1,39 s | 0,119 s | 157,4 tok/s |
| `qwen3.8-27b-unsloth` | 25/25 | 5/5 | 40,35 s | 0,810 s | 25,0 tok/s |

No Gemma, o MTP foi medido com `n-max` de 1 a 4. Todos mantiveram 22/25 e JSON válido em 5/5; `n-max=4` foi o mais rápido, com aproximadamente 80% mais decode e 43% menos latência que o baseline. O Qwen produziu técnicas MITRE e ações mais específicas, mas consumiu de 727 a 1.292 tokens e levou de 29,5 a 50,7 segundos por caso. Foundation-Sec e Ornith consumiram o orçamento em raciocínio sem entregar o contrato JSON de forma confiável nos testes realizados.

Os cinco casos são uma verificação funcional, não uma avaliação estatística. Antes de automatizar decisões, execute um conjunto maior, representativo e rotulado por analistas.

## Arquitetura recomendada

1. Regras determinísticas deduplicam e correlacionam eventos por usuário, host, IP e janela de tempo.
2. O Gemma recebe incidentes compactados e retorna severidade, disposição, confiança e evidências.
3. Casos críticos/altos, inéditos, contraditórios, multi-fonte ou de baixa confiança seguem para o Qwen.
4. Fechamento automático é permitido somente para padrões benignos confirmados por allowlist, CMDB e janela de mudança.
5. A aplicação valida o JSON e mantém auditoria do alerta, prompt, modelo, parâmetros e resposta.

## Autenticação e descoberta

Nunca grave a chave no código ou no Git. Carregue-a no ambiente:

```bash
export LLAMACPP_API_KEY="$(tr -d '\r\n' < /home/eskudo/llm-server/llama/api-key.txt)"
curl -s http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer $LLAMACPP_API_KEY"
```

Toda chamada usa estes headers:

```http
Authorization: Bearer <chave>
Content-Type: application/json
Accept: application/json
```

## Chamada de triagem com Gemma

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $LLAMACPP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4-e2b",
    "messages": [
      {
        "role": "system",
        "content": "Você faz triagem SOC. Use apenas as evidências fornecidas e não invente fatos."
      },
      {
        "role": "user",
        "content": "Um IP externo tentou a mesma senha em 46 contas; ocorreram 44 falhas e 2 sucessos."
      }
    ],
    "temperature": 0,
    "max_tokens": 400,
    "response_format": {
      "type": "json_object",
      "schema": {
        "type": "object",
        "properties": {
          "severity": {
            "type": "string",
            "enum": ["informational", "low", "medium", "high", "critical"]
          },
          "disposition": {
            "type": "string",
            "enum": ["close", "monitor", "escalate"]
          },
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "evidence": {"type": "array", "items": {"type": "string"}},
          "rationale": {"type": "string"},
          "next_actions": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["severity", "disposition", "confidence", "evidence", "rationale", "next_actions"],
        "additionalProperties": false
      }
    }
  }'
```

## Chamada de investigação com Qwen

Envie ao Qwen o resultado da triagem e o conjunto correlacionado de evidências, não cada evento cru:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $LLAMACPP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.8-27b-unsloth",
    "messages": [
      {
        "role": "system",
        "content": "Você é analista sênior SOC. Diferencie fatos de inferências e proponha contenção verificável."
      },
      {
        "role": "user",
        "content": "Triagem: critical, confiança 0.94. Evidências: 9 MFA negados, décimo aprovado, login de ASN inédito e criação de access key IAM."
      }
    ],
    "reasoning_effort": "medium",
    "reasoning_budget": 1536,
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "max_tokens": 2048,
    "stream": false
  }'
```

Esses parâmetros do Qwen já estão definidos no preset do servidor; declará-los na requisição torna a execução explícita e reproduzível. O servidor também suporta JSON Schema, streaming e `reasoning_content`, conforme a [documentação do llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Leitura da resposta

O texto final fica em `choices[0].message.content`; o raciocínio, quando separado pelo template, fica em `choices[0].message.reasoning_content`. Em respostas estruturadas, `content` é uma string contendo JSON e deve passar por uma segunda desserialização. Valide campos e enums na aplicação e trate timeout, HTTP não-2xx, JSON inválido e `finish_reason` diferente de `stop` como falha ou escalonamento manual.

O Gemma suporta quatro requisições concorrentes pelo preset atual. O Qwen possui um slot e deve processar uma investigação por vez para evitar fila descontrolada e contenção de GPU.
