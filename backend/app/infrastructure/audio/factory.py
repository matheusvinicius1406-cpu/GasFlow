"""Factory de providers de áudio — resolve o provider ativo pelas settings.

Default é mock (dev/testes). Produção define STT_PROVIDER=whisper e/ou
TTS_PROVIDER=piper (binários externos; health_check indica disponibilidade).
"""

from app.core.config import settings
from app.domain.audio.provider import SpeechToTextProvider, TextToSpeechProvider
from app.infrastructure.audio.mock_providers import MockSTTProvider, MockTTSProvider
from app.infrastructure.audio.piper_provider import PiperTTSProvider
from app.infrastructure.audio.whisper_provider import WhisperSTTProvider


def get_stt_provider() -> SpeechToTextProvider:
    if settings.stt_provider == "whisper":
        return WhisperSTTProvider(model=settings.whisper_model)
    return MockSTTProvider()


def get_tts_provider() -> TextToSpeechProvider:
    if settings.tts_provider == "piper":
        return PiperTTSProvider(
            voice=settings.piper_voice,
            executable=settings.piper_executable,
            models_dir=settings.piper_models_dir,
        )
    return MockTTSProvider()
