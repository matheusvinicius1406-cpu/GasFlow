# Providers de IA — GasFlow (Ollama / Whisper / Piper)

O backend expõe `/ai/chat`, `/audio/transcribe` e `/audio/process` por meio de
**factories** (`app/infrastructure/ai/factory.py`, `app/infrastructure/audio/factory.py`).
Nenhuma rota instancia provider diretamente; o provider ativo vem das settings.
Default é **mock** (determinístico, para dev/testes) — produção define o real.

```
Settings (AI_PROVIDER / STT_PROVIDER / TTS_PROVIDER)
        │
        ▼
   Factory ──► LLMProvider / SpeechToTextProvider / TextToSpeechProvider
        │          (contratos de domínio — domain/ai, domain/audio)
        ▼
  AIEngine / AudioGateway (regras de negócio nunca tocam o provider)
```

## 1. LLM — Ollama (recomendado, local/on-prem)

### Pré-requisitos

- Ollama instalado: <https://ollama.com/download>
- Modelo baixado: `ollama pull llama3.2`

### Configuração

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434   # host Docker: http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
AI_TIMEOUT_SECONDS=60
AI_MAX_TOKENS=2048
AI_TEMPERATURE=0.3
```

Reinicie o backend (`docker compose restart backend` na stack prod).

### Teste

```bash
curl -X POST http://localhost:8080/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "Quais pedidos estão pendentes hoje?"}'
```

O provider é síncrono (interface de domínio): com workers, a chamada ao
Ollama bloqueia o worker enquanto responde — dimensione `OLLAMA_MODEL` para
o hardware (llama3.2 3B roda bem em CPU modesta; 8B precisa de mais RAM).

### Fallback

- Falha de conexão → `LLMResponse` com `error="LLM_UNAVAILABLE:..."` (a rota
  responde o erro de forma controlada; nenhuma exceção vaza).
- Para voltar ao comportamento determinístico de dev: `AI_PROVIDER=mock`.

## 2. LLM — OpenAI (opcional)

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

O pacote `openai` é importado de forma **lazy** — instale-o apenas se usar
este provider (`pip install openai`). Sem chave/pacote, as chamadas retornam
`OPENAI_MISSING_API_KEY` / `OPENAI_NOT_INSTALLED`.

## 3. STT — Whisper (CLI)

```env
STT_PROVIDER=whisper
WHISPER_MODEL=base
```

Requer o binário `whisper` no PATH do processo (imagem custom ou host).
`health_check()` confere `whisper --help`. Áudio temporário é gravado em
disco, transcrito via subprocess e removido ao final.

## 4. TTS — Piper

```env
TTS_PROVIDER=piper
PIPER_VOICE=pt_BR-faber-medium
PIPER_EXECUTABLE=/usr/local/bin/piper
PIPER_MODELS_DIR=/models     # espera <dir>/<voice>.onnx
```

Baixe a voz (`pt_BR-faber-medium`) e monte o diretório de modelos no
container. Texto entra por stdin; saída `.wav`.

## 5. Verificação de disponibilidade

Cada provider implementa `health_check()`/`health_check()` dos contratos de
domínio. Para auditar o provider ativo e sua saúde:

```bash
python - <<'PY'
from app.core.config import settings
print("LLM:", settings.ai_provider, "| STT:", settings.stt_provider, "| TTS:", settings.tts_provider)
from app.infrastructure.ai.factory import get_llm_provider
from app.infrastructure.audio.factory import get_stt_provider, get_tts_provider
print("llm health:", get_llm_provider().health_check())
print("stt health:", get_stt_provider().health_check())
print("tts health:", get_tts_provider().health_check())
PY
```

## Observabilidade

Uso (tokens quando disponíveis, latência, modelo) é devolvido no
`LLMUsage`/resultado — a camada de IA registra no audit log existente
(`ai_audit_log`). Não há logging de conteúdo sensível.

## Regra de produção

`AI_PROVIDER=mock`/`STT_PROVIDER=mock`/`TTS_PROVIDER=mock` devem existir
apenas em dev/testes. Em produção, configure os reais (ou deixe o serviço
de IA desligado com health check vermelho — a API responde erro controlado).
