"""Piper TTS Provider — implementa TextToSpeechProvider (domain).

Usa o binário `piper` via subprocess (texto via stdin, áudio em .wav).
Modelos ONNX ficam em <models_dir>/<voice>.onnx (default /models).
Falhas viram SpeechResult com erro.
"""

import subprocess
import tempfile
from pathlib import Path

from app.domain.audio.provider import SpeechResult, TextToSpeechProvider


class PiperTTSProvider(TextToSpeechProvider):
    def __init__(self, voice: str = "pt_BR-faber-medium",
                 executable: str = "/usr/local/bin/piper",
                 models_dir: str = "/models") -> None:
        self._voice = voice
        self._executable = executable
        self._models_dir = models_dir.rstrip("/")
        self._available: bool | None = None

    @property
    def provider_name(self) -> str:
        return f"piper-{self._voice}"

    def synthesize(self, text: str, language: str = "pt-BR") -> SpeechResult:
        if not text:
            return SpeechResult(error="TTS_EMPTY_TEXT", provider=self.provider_name)
        if not self.health_check():
            return SpeechResult(error="TTS_UNAVAILABLE", provider=self.provider_name)

        with tempfile.TemporaryDirectory(prefix="gasflow_piper_") as tmp_dir:
            out_path = Path(tmp_dir) / "out.wav"
            cmd = [
                self._executable,
                "--model", f"{self._models_dir}/{self._voice}.onnx",
                "--output_file", str(out_path),
            ]
            try:
                result = subprocess.run(cmd, input=text.encode("utf-8"),
                                        capture_output=True, timeout=120)
            except (subprocess.TimeoutExpired, OSError) as exc:
                return SpeechResult(error=f"TTS_ERROR:{type(exc).__name__}",
                                    provider=self.provider_name)
            if result.returncode != 0:
                return SpeechResult(error="TTS_ERROR:nonzero_exit",
                                    provider=self.provider_name)
            if not out_path.exists():
                return SpeechResult(error="TTS_ERROR:no_output",
                                    provider=self.provider_name)
            audio_bytes = out_path.read_bytes()
            return SpeechResult(
                audio_bytes=audio_bytes,
                mime_type="audio/wav",
                duration_seconds=0.0,
                provider=self.provider_name,
            )

    def health_check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run([self._executable, "--help"],
                                    capture_output=True, timeout=10)
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            self._available = False
        return self._available
