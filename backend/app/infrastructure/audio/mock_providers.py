"""
Mock Audio Providers — FASE 11

Deterministic mock providers for testing without external APIs.
"""

import time
from typing import Dict, Optional
from app.domain.audio.provider import (
    SpeechToTextProvider,
    TextToSpeechProvider,
    TranscriptionResult,
    SpeechResult,
)


class MockSTTProvider(SpeechToTextProvider):
    """Deterministic mock STT provider for testing."""

    def __init__(self, responses: Optional[Dict[str, str]] = None, confidence: float = 0.95, fail: bool = False):
        self._responses = responses or {}
        self._confidence = confidence
        self._fail = fail
        self._call_count = 0
        self._total_latency_ms = 0.0

    @property
    def provider_name(self) -> str:
        return "mock-stt-v1"

    def transcribe(
        self, audio_bytes: bytes, mime_type: str = "audio/ogg", language: str = "pt-BR"
    ) -> TranscriptionResult:
        start = time.time()
        self._call_count += 1

        if self._fail:
            return TranscriptionResult(
                text="",
                confidence=0.0,
                language=language,
                provider=self.provider_name,
                error="STT_UNAVAILABLE",
            )

        if not audio_bytes:
            return TranscriptionResult(
                text="",
                confidence=0.0,
                language=language,
                provider=self.provider_name,
                error="AUDIO_EMPTY",
            )

        # Check for pre-configured responses
        for key, text in self._responses.items():
            if key.lower().encode() in audio_bytes[:100].lower():
                latency = (time.time() - start) * 1000
                self._total_latency_ms += latency
                return TranscriptionResult(
                    text=text,
                    confidence=self._confidence,
                    language=language,
                    duration_seconds=2.0,
                    provider=self.provider_name,
                )

        # Default: use audio bytes as a simple hash to generate text
        # In real testing, use specific test audio fixtures
        text = self._default_transcribe(audio_bytes)
        latency = (time.time() - start) * 1000
        self._total_latency_ms += latency
        return TranscriptionResult(
            text=text,
            confidence=self._confidence,
            language=language,
            duration_seconds=2.0,
            provider=self.provider_name,
        )

    def health_check(self) -> bool:
        return not self._fail

    @property
    def average_latency_ms(self) -> float:
        return self._total_latency_ms / max(self._call_count, 1)

    def set_fail(self, fail: bool):
        self._fail = fail

    def _default_transcribe(self, audio_bytes: bytes) -> str:
        """Default transcription based on audio content pattern."""
        # Simple pattern matching for test audio
        content = audio_bytes[:200].decode("utf-8", errors="ignore").lower()
        if "order" in content or "pedido" in content:
            return "Quero dois P13"
        elif "confirm" in content or "confirmar" in content:
            return "Pode confirmar"
        elif "cancel" in content or "cancelar" in content:
            return "Não quero mais"
        elif "hello" in content or "ola" in content:
            return "Olá, bom dia"
        else:
            return "Mensagem de áudio"


class MockTTSProvider(TextToSpeechProvider):
    """Deterministic mock TTS provider for testing."""

    def __init__(self, fail: bool = False):
        self._fail = fail
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock-tts-v1"

    def synthesize(self, text: str, language: str = "pt-BR") -> SpeechResult:
        self._call_count += 1

        if self._fail:
            return SpeechResult(
                audio_bytes=b"",
                error="TTS_UNAVAILABLE",
                provider=self.provider_name,
            )

        if not text:
            return SpeechResult(
                audio_bytes=b"",
                error="TTS_EMPTY_TEXT",
                provider=self.provider_name,
            )

        # Generate fake audio bytes (OGG header + text hash)
        fake_audio = b"OggS" + text[:100].encode("utf-8")
        return SpeechResult(
            audio_bytes=fake_audio,
            mime_type="audio/ogg",
            duration_seconds=len(text) * 0.05,  # ~50ms per char
            provider=self.provider_name,
        )

    def health_check(self) -> bool:
        return not self._fail

    def set_fail(self, fail: bool):
        self._fail = fail
