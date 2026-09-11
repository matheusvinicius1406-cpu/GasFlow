"""
Audio API — FASE 11

POST /audio/transcribe — Transcribe audio message
POST /audio/process — Process audio through full pipeline
GET /audio/metrics — Audio processing metrics
"""

import base64
from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional

from app.domain.audio.media import AudioMessage
from app.domain.audio.provider import SpeechToTextProvider, TextToSpeechProvider
from app.infrastructure.audio.factory import get_stt_provider, get_tts_provider
from app.application.audio.gateway import AudioGateway

router = APIRouter(prefix="/audio", tags=["audio"])

# ── Singletons ──────────────────────────────────────────

_stt_provider: Optional[SpeechToTextProvider] = None
_tts_provider: Optional[TextToSpeechProvider] = None
_audio_gateway: Optional[AudioGateway] = None


def _get_stt() -> SpeechToTextProvider:
    global _stt_provider
    if _stt_provider is None:
        _stt_provider = get_stt_provider()
    return _stt_provider


def _get_tts() -> TextToSpeechProvider:
    global _tts_provider
    if _tts_provider is None:
        _tts_provider = get_tts_provider()
    return _tts_provider


def _get_gateway(conversation_gateway=None) -> AudioGateway:
    global _audio_gateway
    if _audio_gateway is None:
        _audio_gateway = AudioGateway(
            stt_provider=_get_stt(),
            tts_provider=_get_tts(),
            conversation_gateway=conversation_gateway,
        )
    return _audio_gateway


# ── Schemas ─────────────────────────────────────────────


class TranscribeRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64-encoded audio")
    mime_type: str = Field("audio/ogg")
    language: str = Field("pt-BR")


class TranscribeResponse(BaseModel):
    text: str
    confidence: float
    language: str
    duration_seconds: float
    provider: str
    error: Optional[str] = None


class AudioProcessRequest(BaseModel):
    account_id: str = Field("primary")
    sender_phone: str = Field(..., min_length=8, max_length=20)
    provider_message_id: str = Field(..., min_length=1)
    audio_base64: str = Field(..., description="Base64-encoded audio")
    mime_type: str = Field("audio/ogg")
    file_size_bytes: int = Field(0)
    duration_seconds: float = Field(0.0)


class AudioProcessResponse(BaseModel):
    status: str
    transcription: Optional[str] = None
    confidence: float = 0.0
    outbound_text: Optional[str] = None
    outbound_to: Optional[str] = None
    error: Optional[str] = None
    conversation_id: Optional[int] = None


# ── Endpoints ───────────────────────────────────────────


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(req: TranscribeRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """Transcribe audio to text using STT provider."""
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 audio") from exc

    stt = _get_stt()
    result = stt.transcribe(audio_bytes, mime_type=req.mime_type, language=req.language)
    return TranscribeResponse(
        text=result.text,
        confidence=result.confidence,
        language=result.language,
        duration_seconds=result.duration_seconds,
        provider=result.provider,
        error=result.error,
    )


@router.post("/process", response_model=AudioProcessResponse)
async def process_audio(req: AudioProcessRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """Process audio through full pipeline: STT → Conversation Gateway → AI."""
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 audio") from exc

    audio_msg = AudioMessage(
        provider_message_id=req.provider_message_id,
        account_id=req.account_id,
        sender_phone=req.sender_phone,
        mime_type=req.mime_type,
        file_size_bytes=req.file_size_bytes,
        duration_seconds=req.duration_seconds,
    )

    gateway = _get_gateway()
    result = gateway.process_audio(audio_msg, audio_bytes)
    return AudioProcessResponse(
        status=result.get("status", "error"),
        transcription=result.get("transcription"),
        confidence=result.get("confidence", 0.0),
        outbound_text=result.get("outbound_text"),
        outbound_to=req.sender_phone if result.get("outbound_text") else None,
        error=result.get("error"),
        conversation_id=result.get("conversation_id"),
    )


@router.get("/metrics")
async def get_audio_metrics(ctx: TenantContext = Depends(get_tenant_context)):
    """Get audio processing metrics."""
    gateway = _get_gateway()
    return gateway.get_metrics()
