"""Testes determinísticos dos providers de IA/áudio (fábricas + Ollama).

Não dependem de Ollama/Whisper/Piper reais: transporte HTTP e subprocess
são stubados. Validam o contrato de domínio (LLMProvider/STT/TTS) e a
resolução por settings (AI_PROVIDER / STT_PROVIDER / TTS_PROVIDER).
"""

import httpx

from app.core.config import settings
from app.domain.ai.provider import LLMMessage, LLMRole, LLMResponse
from app.infrastructure.ai.factory import get_llm_provider
from app.infrastructure.ai.mock_provider import MockLLMProvider
from app.infrastructure.ai.ollama_provider import OllamaProvider
from app.infrastructure.ai.openai_provider import OpenAIProvider
from app.infrastructure.audio.factory import get_stt_provider, get_tts_provider
from app.infrastructure.audio.mock_providers import MockSTTProvider, MockTTSProvider
from app.infrastructure.audio.piper_provider import PiperTTSProvider
from app.infrastructure.audio.whisper_provider import WhisperSTTProvider


# ── Factory LLM ─────────────────────────────────────────────


def test_factory_default_returns_mock():
    assert isinstance(get_llm_provider(), MockLLMProvider)


def test_factory_ollama(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "ollama")
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider._base_url == settings.ollama_base_url.rstrip("/")
    assert provider.model_name == settings.ollama_model


def test_factory_openai(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    provider = get_llm_provider()
    assert isinstance(provider, OpenAIProvider)


def test_factory_unknown_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "xpto")
    assert isinstance(get_llm_provider(), MockLLMProvider)


# ── OllamaProvider (httpx stubado) ──────────────────────────


class _FakeResponse:
    def __init__(self, payload=None, ok=True):
        self._payload = payload or {}
        self._ok = ok
        self.status_code = 200 if ok else 500

    def raise_for_status(self):
        if not self._ok:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(500, request=httpx.Request("POST", "http://x")),
            )

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.post_payload = None
        self.get_status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None):
        self.post_url = url
        self.post_payload = json
        if getattr(self, "raise_connect", False):
            raise httpx.ConnectError("connection refused")
        return _FakeResponse(
            {
                "message": {"content": "Olá, GasFlow!"},
                "prompt_eval_count": 12,
                "eval_count": 5,
                "done_reason": "stop",
            }
        )

    def get(self, url):
        self.get_url = url
        if not self.get_status == 200:
            raise httpx.ConnectError("down")
        return _FakeResponse()


def _patch_httpx(monkeypatch, client=None):
    import app.infrastructure.ai.ollama_provider as mod

    fake = client or _FakeClient()
    monkeypatch.setattr(mod.httpx, "Client", lambda *a, **k: fake)
    return fake


def test_ollama_generate_success(monkeypatch):
    fake = _patch_httpx(monkeypatch)
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")
    result = provider.generate([LLMMessage(role=LLMRole.USER, content="oi")])
    assert isinstance(result, LLMResponse)
    assert result.content == "Olá, GasFlow!"
    assert result.error is None
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 5
    # payload trafega no formato /api/chat do Ollama
    assert fake.post_payload["model"] == "llama3.2"
    assert fake.post_payload["stream"] is False
    assert fake.post_payload["messages"][0]["role"] == "user"
    assert fake.post_url == "http://localhost:11434/api/chat"


def test_ollama_generate_unavailable_returns_error(monkeypatch):
    fake = _FakeClient()
    fake.raise_connect = True
    _patch_httpx(monkeypatch, fake)
    provider = OllamaProvider()
    result = provider.generate([LLMMessage(role=LLMRole.USER, content="oi")])
    assert result.content == ""
    assert result.error and "LLM_UNAVAILABLE" in result.error


def test_ollama_health_check(monkeypatch):
    _patch_httpx(monkeypatch)
    provider = OllamaProvider()
    assert provider.health_check() is True

    fake = _FakeClient()
    fake.get_status = 500
    _patch_httpx(monkeypatch, fake)
    assert provider.health_check() is False


# ── Factory áudio ───────────────────────────────────────────


def test_audio_factories_default_are_mock():
    assert isinstance(get_stt_provider(), MockSTTProvider)
    assert isinstance(get_tts_provider(), MockTTSProvider)


def test_audio_factories_select_real(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "whisper")
    monkeypatch.setattr(settings, "tts_provider", "piper")
    stt = get_stt_provider()
    tts = get_tts_provider()
    assert isinstance(stt, WhisperSTTProvider)
    assert isinstance(tts, PiperTTSProvider)
    assert stt._model == settings.whisper_model
    assert tts._voice == settings.piper_voice


# ── Whisper / Piper (health e caminhos de erro, subprocess stubado) ──


def test_whisper_health_check_false_when_binary_missing(monkeypatch):
    import subprocess

    def _raise(*args, **kwargs):
        raise FileNotFoundError("whisper not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    provider = WhisperSTTProvider()
    assert provider.health_check() is False
    # transcribe com provider indisponível → erro controlado, sem exceção
    result = provider.transcribe(b"fake-audio", language="pt-BR")
    assert result.error == "STT_UNAVAILABLE"


def test_whisper_transcribe_empty_audio(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "mock")  # não toca binário
    provider = WhisperSTTProvider()
    provider._available = False  # garante short-circuit no health
    result = provider.transcribe(b"", language="pt-BR")
    assert result.error == "AUDIO_EMPTY"


def test_piper_synthesize_empty_text():
    provider = PiperTTSProvider()
    result = provider.synthesize("")
    assert result.error == "TTS_EMPTY_TEXT"
    assert not result.is_valid


def test_piper_health_check_false_when_binary_missing(monkeypatch):
    import subprocess

    def _raise(*args, **kwargs):
        raise FileNotFoundError("piper not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    provider = PiperTTSProvider()
    assert provider.health_check() is False


def test_piper_synthesize_error_path(monkeypatch):
    import subprocess

    class _Result:
        returncode = 1
        stderr = b"piper exploded"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
    provider = PiperTTSProvider()
    provider._available = True  # simula binário presente
    result = provider.synthesize("Olá")
    assert result.error == "TTS_ERROR:nonzero_exit"
    assert not result.is_valid
