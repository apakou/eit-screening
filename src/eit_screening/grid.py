"""Grille d'évaluation (critères et Concerns), lue dans un fichier de configuration.

Les critères viennent du mémoire et non d'un document de MEST ; les Concerns,
eux, sont les huit drapeaux du tableau de bord de revue de la cohorte 2027. Rien
n'est codé en dur, pour pouvoir être remplacé sans toucher au code.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Criterion(BaseModel):
    key: str
    name: str
    max_points: int
    query: str


class Concern(BaseModel):
    """Drapeau d'alerte du tableau de bord de revue de MEST.

    ``detection`` dit comment le prototype produit ce drapeau :
    ``controle`` (règle déterministe des étapes 1 et 2), ``modele`` (jugement du
    modèle de langage, avec citation vérifiée) ou ``manuel`` (aucune détection
    automatique : l'évaluateur le coche lui-même).
    """

    key: str
    name: str
    detection: Literal["controle", "modele", "manuel"] = "manuel"


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
