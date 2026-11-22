"""Configuration du découpage, des embeddings et de Qdrant."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class ChunkingRule(BaseModel):
    max_words: int = 120
    overlap_words: int = 20
    sections: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ChunkingRule:
        if not 0 <= self.overlap_words < self.max_words:
            raise ValueError("Le recouvrement doit être positif et plus petit que la taille d'un passage.")
        return self


class EmbeddingRule(BaseModel):
    model: str = "BAAI/bge-m3"
    revision: str
    max_tokens: int = 512
    batch_size: int = 8


class QdrantRule(BaseModel):
    url: str = ""
    path: str = "data/qdrant-local"
    collection: str = "passages"


class SearchConfig(BaseModel):
    chunking: ChunkingRule = Field(default_factory=ChunkingRule)
    embedding: EmbeddingRule
    qdrant: QdrantRule = Field(default_factory=QdrantRule)


def load_config(path: Path | str | None = None) -> SearchConfig:
    """Lit la configuration ; sans chemin, prend le fichier livré avec le module."""
    if path is None:
        raw = resources.files(__package__).joinpath("search.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return SearchConfig.model_validate(tomllib.loads(raw.decode("utf-8")))
