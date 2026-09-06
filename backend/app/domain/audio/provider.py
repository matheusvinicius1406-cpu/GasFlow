"""
Audio Provider Interfaces — FASE 11

Speech-to-Text and Text-to-Speech provider abstractions.
Never couple domain to specific provider (Whisper, OpenAI, Google, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class AudioFormat(str, Enum):
    OGG = "OGG"
    WAV = "WAV"
    MP3 = "MP3"
    AAC = "AAC"
    OPUS = "OPUS"
    UNKNOWN = "UNKNOWN"


# ── STT ─────────────────────────────────────────────────


@dataclass
class TranscriptionResult:
    """Result of speech-to-text transcription."""

    text: str
    confidence: float = 0.0  # 0.0 to 1.0
    language: str = "pt-BR"
    duration_seconds: float = 0.0
    provider: str = ""
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return bool(self.text) and not self.error

    @property
    def is_low_confidence(self) -> bool:
        return 0.0 < self.confidence < 0.5


class SpeechToTextProvider(ABC):
    """Abstract STT provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def transcribe(
        self, audio_bytes: bytes, mime_type: str = "audio/ogg", language: str = "pt-BR"
    ) -> TranscriptionResult:
        """Transcribe audio to text."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is available."""
        pass

    @property
    def supported_formats(self):
        return ["audio/ogg", "audio/wav", "audio/mp3", "audio/aac"]


# ── TTS ─────────────────────────────────────────────────


@dataclass
class SpeechResult:
    """Result of text-to-speech synthesis."""

    audio_bytes: bytes = b""
    mime_type: str = "audio/ogg"
    duration_seconds: float = 0.0
    provider: str = ""
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return bool(self.audio_bytes) and not self.error


class TextToSpeechProvider(ABC):
    """Abstract TTS provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def synthesize(self, text: str, language: str = "pt-BR") -> SpeechResult:
        """Convert text to speech audio."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is available."""
        pass
