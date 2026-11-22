"""Configuration de la lecture des pièces jointes et de la transcription."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AttachmentRule(BaseModel):
    ocr_engine: Literal["auto", "rapidocr", "tesseract"] = "auto"
    tesseract_languages: list[str] = Field(default_factory=lambda: ["eng"])


class TranscriptionRule(BaseModel):
    model: str = "small"
    compute_type: str = "int8"
    language: str = ""
    beam_size: int = 5


class VideoRule(BaseModel):
    personal_statement: str = "personal_statement"
    assessment_reflection: str = "assessment_reflection"
    extensions: list[str] = Field(default_factory=lambda: [".mp4", ".mov", ".webm"])


class MediaConfig(BaseModel):
    attachments: AttachmentRule = Field(default_factory=AttachmentRule)
    transcription: TranscriptionRule = Field(default_factory=TranscriptionRule)
    videos: VideoRule = Field(default_factory=VideoRule)


def load_config(path: Path | str | None = None) -> MediaConfig:
    """Lit la configuration ; sans chemin, prend le fichier livré avec le module."""
    if path is None:
        raw = resources.files(__package__).joinpath("media.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return MediaConfig.model_validate(tomllib.loads(raw.decode("utf-8")))
