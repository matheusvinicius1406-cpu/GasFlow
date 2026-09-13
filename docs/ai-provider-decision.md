# Decisão — Provider de IA (Fase 4.2)

**Data:** 2026-09-13
**Status:** DECIDIDO — Ollama como único provider (MVP). Fallback keyless **adiado** com condições de reabertura.
**Reversibilidade:** alta — a troca é uma env var (`AI_PROVIDER`); a interface de domínio `LLMProvider` permite plugar outro provider sem tocar regras de negócio.

---

## Decisão

**Somente Ollama** (sem fallback externo no MVP):

| Uso | Modelo | Motivo |
|---|---|---|
| Classificação de intenção / tool-calling (JSON curto) | `qwen3:0.6b` | Rápido (~20 tok/s CPU), 1 GB RAM, JSON confiável |
| Resposta conversacional do Copilot | `qwen3:1.7b` | Português melhor que o 0.6b, 1.9 GB RAM, ~11 tok/s CPU (aceitável) |

**Fallback = degradação graciosa já implementada** (`LLMResponse.error="LLM_UNAVAILABLE:..."` + mensagem controlada na UI), não um provider externo. O fallback "de verdade" fica adiado — ver abaixo.

**Toggle admin:** a IA deve poder ser desativada pelo admin (restrição de projeto). Hoje isso é `AI_PROVIDER=mock` no boot; a tela de admin deve expor esse controle (P1, junto do módulo de Inteligência).

---

## Por que não os fallbacks "keyless" agora

### `ainative-openai` — DESCLASSIFICADO (deixou de ser grátis)

O site (`ainative.studio`) agora cobra **US$ 5/mês** (trial de 3 dias; Hobbyist $5, Pro $49, Business $149). O claim "free" na descrição do pacote npm está **desatualizado**. Não é mais opção de fallback gratuito; a $5/mo compete com OpenAI/DeepSeek pagos, que têm SLA — não vale o risco de um proxy desconhecido.

### `keylessai` — ADIADO (risco de privacidade real)

Funciona e é MIT, mas o design é incompatível com os dados do GasFlow:

1. **Os dados saem da máquina.** O endpoint hospedado roteia para **endpoints públicos anônimos de terceiros** (Pollinations.ai, ApiAirforce) através de um Cloudflare Worker de **um único mantenedor** (`lordbasilaiassistant-sudo`, contato Gmail pessoal). Perguntas do Copilot carregam nomes de clientes, endereços e histórico de pedidos do depósito — iriam para serviços anônimos sem contrato, sem DPA e sem garantia de não-treinamento.
2. **Sem estabilidade:** sem ToS comercial, concorrência de 1 request/IP, 100k req/dia no free tier do Cloudflare *do mantenedor* (degrada para 429), e os upstreams ("more as they appear") podem sumir sem aviso. O próprio README documenta injeção de anúncios/avisos nas respostas dos upstreams, que o proxy filtra — frágil por construção.
3. **É exatamente o risco do ROADMAP_BLOCKERS item 9:** "dados de clientes indo para endpoint de terceiros exige toggle admin default-off + audit_log de uso".

### Condições para reabrir o fallback keyless (P2+, nunca default)

- [ ] Toggle admin **default-OFF** + `audit_log` de cada uso (já previsto no roadmap)
- [ ] Análise de dados enviados: máscara/anonimização antes de sair da máquina (sem PII de clientes no prompt)
- [ ] Verificação dos ToS dos upstreams reais (Pollinations/ApiAirforce) para uso comercial
- [ ] Alternativa preferível: **worker self-hosted** (o repo do keylessai permite fork + `wrangler deploy` na própria conta Cloudflare) — reduz o risco de o mantenedor sumir, mas o ponto 1 (dados → terceiros anônimos) permanece

---

## Números medidos (hoje, máquina-alvo, CPU only, sem GPU)

| Modelo | RAM carregada | Throughput | Tarefa de referência | Resultado |
|---|---|---|---|---|
| `qwen3:0.6b` | 1.02 GB | ~20 tok/s | Classificação de intenção → JSON | ✅ 3/3 válidos, 0.65–1.1 s |
| `qwen3:1.7b` | 1.88 GB | ~11 tok/s | Resposta conversacional curta | ✅ 2.1 s |

**Achado crítico de operação:** os modelos `qwen3` têm *thinking mode* ativo por padrão neste Ollama. Sem controle, o budget de tokens é queimado no campo `thinking` e **o `content` volta vazio** (`done_reason: length`). A flag `/no_think` no prompt foi **ignorada** pela build local. O controle que funciona é a opção de API:

```json
{ "model": "qwen3:0.6b", "stream": false, "think": false, "options": { "num_predict": 128 } }
```

**Ação de código (única, barata):** ✅ **RESOLVIDO** — `app/infrastructure/ai/ollama_provider.py` agora envia `"think": false` no payload do `/api/chat` (configurável via `OLLAMA_THINK=false|true|auto`, default `false`) e nunca mapeia `message.thinking` para `LLMResponse.content`. Validado contra o Ollama real da máquina-alvo: com o fix, classificação de intenção retorna JSON válido (`finish: stop`); sem o fix, `content` volta vazio (`finish: length`).

### Dimensionamento

- Ambos os modelos rodam em CPU puro na máquina-alvo (8 GB RAM é suficiente; 16 GB confortável com backend + Electron).
- Resposta de ~200 tokens no 1.7b ≈ 18 s — aceitável para o Copilot; para classificação use o 0.6b (~1 s).
- O provider é **síncrono** (interface de domínio): bloqueia o worker durante a chamada — já documentado em `ollama-setup.md`.
- `ollama pull qwen3:0.6b qwen3:1.7b` deve fazer parte do checklist de instalação do depósito (modelos não vão no instalador).

---

## Configuração de produção

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:1.7b          # conversacional; classificação usa 0.6b via rota própria quando implementado
AI_TIMEOUT_SECONDS=60
AI_MAX_TOKENS=512
AI_TEMPERATURE=0.3
```

Mock (`AI_PROVIDER=mock`) permanece apenas para dev/testes, conforme `ollama-setup.md`.

---

## Trade-offs aceitos

| Escolha | Ganho | Custo |
|---|---|---|
| Ollama local, sem fallback externo | Zero custo, dados nunca saem da máquina, LGPD-friendly | Sem internet não degrada para nuvem; qualidade do 1.7b < GPT-4o para respostas longas |
| qwen3 em vez de llama3.2 | Menor RAM, thinking desligável, tools | Precisa `"think": false` explícito no provider (fix único) |
| Fallback keyless adiado | Sem risco de privacidade/estabilidade no MVP | Copilot indisponível se o Ollama cair (mensagem controlada, sem dados perdidos) |

## Próximos passos ligados a esta decisão

1. **P1 (5.3 Inteligência):** ✅ fix `"think": false` no `OllamaProvider` concluído (commit deste doc); restam toggle admin de IA + `audit_log` de uso.
2. **Instalação:** incluir `ollama pull` no checklist do depósito (docs de setup).
3. **P2:** reavaliar fallback keyless apenas se as condições acima forem atendidas.
