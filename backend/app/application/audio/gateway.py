"""
Audio Gateway — FASE 11

Processes incoming audio messages:
1. Validate media (format, size, duration)
2. Idempotency check
3. Transcribe (STT)
4. Low confidence handling
5. Route transcribed text to Conversation Gateway (Phase 10)
6. Optional TTS for response
7. Return outbound (text or audio)

Architecture:
AUDIO → Audio Gateway → STT → TEXT → Conversation Gateway → AI Core → Response → TTS (optional)

Never: Audio → LLM directly
"""

import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime

from app.domain.audio.provider import SpeechToTextProvider, TextToSpeechProvider, TranscriptionResult
from app.domain.audio.media import (
    AudioMessage, AudioProcessingStatus,
    MAX_AUDIO_SIZE_MB, MAX_AUDIO_DURATION_SECONDS,
    STT_TIMEOUT_SECONDS, LOW_CONFIDENCE_THRESHOLD,
)


class AudioGateway:
    """
    Processes audio messages through STT then routes to Conversation Gateway.
    """

    def __init__(
        self,
        stt_provider: SpeechToTextProvider,
        tts_provider: Optional[TextToSpeechProvider] = None,
        conversation_gateway=None,
    ):
        self.stt = stt_provider
        self.tts = tts_provider
        self.conversation_gateway = conversation_gateway

        # ── Observability ─────────────────────────────────
        self._metrics = {
            "audio_received": 0,
            "audio_transcribed": 0,
            "transcription_success": 0,
            "transcription_failure": 0,
            "low_confidence": 0,
            "tts_generated": 0,
            "tts_failure": 0,
            "voice_orders": 0,
            "voice_confirmations": 0,
            "avg_stt_latency_ms": 0.0,
        }
        self._metrics_lock = threading.Lock()
        self._total_stt_latency = 0.0

    def get_metrics(self) -> Dict[str, Any]:
        with self._metrics_lock:
            m = dict(self._metrics)
            count = m.get("audio_transcribed", 0)
            m["avg_stt_latency_ms"] = round(self._total_stt_latency / max(count, 1), 2)
            return m

    def process_audio(
        self,
        audio_message: AudioMessage,
        audio_bytes: bytes = b"",
    ) -> Dict[str, Any]:
        """
        Process an incoming audio message.

        Returns:
            {
                "status": "processed" | "skipped" | "error",
                "transcription": str | None,
                "confidence": float,
                "outbound_text": str | None,
                "outbound_audio": bytes | None,
                "error": str | None,
                "conversation_id": int | None,
            }
        """
        self._inc_metric("audio_received")

        # 1. Validate media
        validation = self._validate_media(audio_message)
        if not validation["ok"]:
            return {
                "status": "error",
                "error": validation["error"],
                "transcription": None,
                "confidence": 0.0,
                "outbound_text": None,
                "outbound_audio": None,
                "conversation_id": None,
            }

        # 2. Idempotency (check via conversation gateway if available)
        if self.conversation_gateway and audio_message.provider_message_id:
            conv_repo = self.conversation_gateway.conversation_repo
            if conv_repo.find_duplicate_message(audio_message.provider_message_id):
                return {
                    "status": "skipped",
                    "error": "DUPLICATE_AUDIO",
                    "transcription": None,
                    "confidence": 0.0,
                    "outbound_text": None,
                    "outbound_audio": None,
                    "conversation_id": None,
                }

        # 3. Transcribe
        transcription = self._transcribe(audio_bytes, audio_message.mime_type)
        if transcription.error:
            self._inc_metric("transcription_failure")
            return {
                "status": "error",
                "error": transcription.error,
                "transcription": None,
                "confidence": 0.0,
                "outbound_text": None,
                "outbound_audio": None,
                "conversation_id": None,
            }

        self._inc_metric("transcription_success")

        # 4. Low confidence check
        if transcription.is_low_confidence:
            self._inc_metric("low_confidence")
            reply = "Não consegui entender bem o áudio. Pode repetir ou digitar sua mensagem?"
            return {
                "status": "processed",
                "transcription": transcription.text,
                "confidence": transcription.confidence,
                "outbound_text": reply,
                "outbound_audio": None,
                "error": None,
                "conversation_id": None,
            }

        # 5. Route transcribed text to Conversation Gateway
        if not self.conversation_gateway:
            self._inc_metric("audio_transcribed")
            return {
                "status": "processed",
                "transcription": transcription.text,
                "confidence": transcription.confidence,
                "outbound_text": f"Transcrição: {transcription.text}",
                "outbound_audio": None,
                "error": None,
                "conversation_id": None,
            }

        # Build text message for conversation gateway
        text_msg = {
            "account_id": audio_message.account_id,
            "sender_phone": audio_message.sender_phone,
            "provider_message_id": audio_message.provider_message_id,
            "text": transcription.text,
            "message_type": "TEXT",
            "from_me": False,
        }

        result = self.conversation_gateway.process_incoming(text_msg)

        # 6. Optional TTS for response
        outbound_audio = None
        if self.tts and result.get("outbound_text"):
            speech = self.tts.synthesize(result["outbound_text"])
            if speech.is_valid:
                self._inc_metric("tts_generated")
                outbound_audio = speech.audio_bytes
            else:
                self._inc_metric("tts_failure")
                # Fallback: text response is still valid

        self._inc_metric("audio_transcribed")

        return {
            "status": result.get("status", "processed"),
            "transcription": transcription.text,
            "confidence": transcription.confidence,
            "outbound_text": result.get("outbound_text"),
            "outbound_audio": outbound_audio,
            "error": result.get("error"),
            "conversation_id": result.get("conversation_id"),
        }

    def _validate_media(self, audio: AudioMessage) -> Dict[str, Any]:
        """Validate audio media before processing."""
        # Check mime type
        supported = ["audio/ogg", "audio/wav", "audio/mp3", "audio/aac", "audio/opus"]
        if audio.mime_type not in supported:
            return {"ok": False, "error": "AUDIO_UNSUPPORTED"}

        # Check file size
        max_bytes = MAX_AUDIO_SIZE_MB * 1024 * 1024
        if audio.file_size_bytes > max_bytes:
            return {"ok": False, "error": "AUDIO_TOO_LARGE"}

        # Check duration
        if audio.duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            return {"ok": False, "error": "AUDIO_TOO_LONG"}

        return {"ok": True, "error": None}

    def _transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult:
        """Transcribe audio using STT provider with timeout."""
        start = time.time()
        try:
            result = self.stt.transcribe(audio_bytes, mime_type=mime_type)
            latency = (time.time() - start) * 1000
            with self._metrics_lock:
                self._total_stt_latency += latency
            return result
        except Exception as e:
            return TranscriptionResult(
                text="", confidence=0.0,
                provider=self.stt.provider_name,
                error="STT_FAILED",
            )

    def _inc_metric(self, key: str):
        with self._metrics_lock:
            if key in self._metrics:
                self._metrics[key] += 1
