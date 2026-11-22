"""Transcription des vidéos : extraction de l'audio par FFmpeg, puis faster-whisper.

Chaque segment garde son horodatage (début et fin, en secondes) et les valeurs
de confiance de Whisper. Pour les dossiers fictifs, il n'y a pas de vidéo : la
transcription est lue dans un fichier texte, et ses segments n'ont pas
d'horodatage (``None``). Aucun horodatage n'est inventé.
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import MediaConfig, TranscriptionRule, load_config

SAMPLE_RATE = 16_000


class Segment(BaseModel):
    start: float | None = None
    end: float | None = None
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


class Transcript(BaseModel):
    source: Literal["faster-whisper", "text_file"]
    model: str | None = None
    language: str | None = None
    language_probability: float | None = None
    duration: float | None = None
    segments: list[Segment] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments if segment.text.strip())


def extract_audio(video: Path | str, wav: Path | str) -> Path:
    """Piste audio en WAV mono 16 kHz, le format attendu par Whisper."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
               "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", str(wav)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg n'a pas pu extraire l'audio de {video} : {result.stderr.strip()}")
    return Path(wav)


def load_wav(path: Path | str):
    """Signal d'un WAV mono 16 bits, en flottants entre -1 et 1.

    Lu ici plutôt que par faster-whisper : son décodeur (PyAV) n'accepte pas la
    version de PyAV installée, et FFmpeg a déjà fait la conversion.
    """
    import numpy as np

    with wave.open(str(path)) as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getframerate() != SAMPLE_RATE:
            raise ValueError(f"{path} : WAV mono 16 bits à {SAMPLE_RATE} Hz attendu.")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


@cache
def _model(name: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type=compute_type)


def transcribe_audio(wav: Path | str, rule: TranscriptionRule) -> Transcript:
    model = _model(rule.model, rule.compute_type)
    segments, info = model.transcribe(load_wav(wav), language=rule.language or None, beam_size=rule.beam_size)
    return Transcript(
        source="faster-whisper",
        model=rule.model,
        language=info.language,
        language_probability=round(info.language_probability, 3),
        duration=round(info.duration, 2),
        segments=[
            Segment(
                start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip(),
                avg_logprob=round(s.avg_logprob, 3), no_speech_prob=round(s.no_speech_prob, 3),
            )
            for s in segments
        ],
    )


def transcribe_video(video: Path | str, config: MediaConfig | None = None) -> Transcript:
    """Transcrit une vidéo (ou un fichier audio) ; le WAV intermédiaire est effacé."""
    config = config or load_config()
    with tempfile.TemporaryDirectory(prefix="eit-audio-") as folder:
        wav = extract_audio(video, Path(folder) / "audio.wav")
        return transcribe_audio(wav, config.transcription)


def read_text_transcript(path: Path | str) -> Transcript:
    """Transcription déjà écrite (dossiers fictifs) : un seul segment, sans horodatage."""
    text = Path(path).read_text(encoding="utf-8").strip()
    return Transcript(source="text_file", segments=[Segment(text=text)] if text else [])
