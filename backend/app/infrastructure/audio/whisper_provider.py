"""Whisper STT Provider — implementa SpeechToTextProvider (domain).

Usa o CLI `whisper` (openai-whisper ou whisper.cpp) via subprocess.
Sem dependência Python extra; o binário precisa estar no PATH quando
STT_PROVIDER=whisper. Falhas viram TranscriptionResult com erro.
"""

import subprocess
import tempfile
from pathlib import Path

from app.domain.audio.provider import SpeechToTextProvider, TranscriptionResult

_EXT_BY_MIME = {
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mp3": ".mp3",
    "audio/aac": ".aac",
    "audio/mpeg": ".mp3",
}


class WhisperSTTProvider(SpeechToTextProvider):
    def __init__(self, model: str = "base", executable: str = "whisper") -> None:
        self._model = model
        self._executable = executable
        self._available: bool | None = None

    @property
    def provider_name(self) -> str:
        return f"whisper-{self._model}"

    def transcribe(
        self, audio_bytes: bytes, mime_type: str = "audio/ogg", language: str = "pt-BR"
    ) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", error="AUDIO_EMPTY", language=language, provider=self.provider_name)
        if not self.health_check():
            return TranscriptionResult(text="", error="STT_UNAVAILABLE", language=language, provider=self.provider_name)

        ext = _EXT_BY_MIME.get(mime_type, ".wav")
        with tempfile.TemporaryDirectory(prefix="gasflow_whisper_") as tmp_dir:
            audio_path = Path(tmp_dir) / f"audio{ext}"
            audio_path.write_bytes(audio_bytes)
            lang = language.split("-")[0] if language else "pt"
            cmd = [
                self._executable,
                str(audio_path),
                "--model",
                self._model,
                "--language",
                lang,
                "--output_format",
                "txt",
                "--output_dir",
                tmp_dir,
                "--task",
                "transcribe",
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=300)
            except (subprocess.TimeoutExpired, OSError) as exc:
                return TranscriptionResult(
                    text="", error=f"STT_ERROR:{type(exc).__name__}", language=language, provider=self.provider_name
                )
            if result.returncode != 0:
                return TranscriptionResult(
                    text="", error="STT_ERROR:nonzero_exit", language=language, provider=self.provider_name
                )
            transcript_path = Path(tmp_dir) / f"{audio_path.stem}.txt"
            text = ""
            if transcript_path.exists():
                text = transcript_path.read_text(encoding="utf-8").strip()
            return TranscriptionResult(
                text=text,
                confidence=1.0,
                language=language,
                duration_seconds=0.0,
                provider=self.provider_name,
            )

    def health_check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run([self._executable, "--help"], capture_output=True, timeout=10)
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            self._available = False
        return self._available
