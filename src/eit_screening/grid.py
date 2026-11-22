"""Grille d'évaluation (critères et Concerns), lue dans un fichier de configuration.

La grille vient du mémoire et non d'un document de MEST : elle n'est jamais
codée en dur, pour pouvoir être remplacée sans toucher au code.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Criterion(BaseModel):
    key: str
    name: str
    max_points: int
    query: str


class Concern(BaseModel):
    key: str
    name: str


class Grid(BaseModel):
    total_points: int
    criteria: list[Criterion]
    concerns: list[Concern] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_total(self) -> Grid:
        if sum(c.max_points for c in self.criteria) != self.total_points:
            raise ValueError("La somme des points des critères ne correspond pas au total de la grille.")
        return self


def load_grid(path: Path | str | None = None) -> Grid:
    """Lit la grille ; sans chemin, prend ``grille.toml`` livré avec le paquet."""
    if path is None:
        raw = resources.files("eit_screening").joinpath("grille.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return Grid.model_validate(tomllib.loads(raw.decode("utf-8")))
