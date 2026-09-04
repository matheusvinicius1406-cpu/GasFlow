"""
Audio Media — FASE 11

Represents an audio message in the system.
Audio is UNTRUSTED INPUT — same security rules as text.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class AudioProcessingStatus(str, Enum):
    RECEIVED = "RECEIVED"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class AudioMessage:
    """Audio message received from WhatsApp."""
    id: Optional[int] = None
    provider_message_id: str = ""
    account_id: str = "primary"
    sender_phone: str = ""
    media_url: Optional[str] = None
    mime_type: str = "audio/ogg"
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    status: AudioProcessingStatus = AudioProcessingStatus.RECEIVED
    transcription: Optional[str] = None
    transcription_confidence: float = 0.0
    transcription_language: str = "pt-BR"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


# ── Limits ──────────────────────────────────────────────
MAX_AUDIO_SIZE_MB = 16
MAX_AUDIO_DURATION_SECONDS = 300  # 5 minutes
AUDIO_TTL_HOURS = 1  # Temporary file retention
STT_TIMEOUT_SECONDS = 30
TTS_TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
LOW_CONFIDENCE_THRESHOLD = 0.5
