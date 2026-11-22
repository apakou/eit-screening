"""Éléments partagés par les contrôles : constats, citations, outils de comparaison."""

from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# alert : les données montrent qu'un critère n'est pas rempli.
# to_check : donnée manquante, illisible, ambiguë ou suspecte ; un humain doit regarder.
Severity = Literal["alert", "to_check"]
SEVERITY_LABELS: dict[str, str] = {"alert": "alerte", "to_check": "à vérifier"}


class Evidence(BaseModel):
    """Élément sur lequel s'appuie un constat, cité tel qu'il est écrit dans sa source.

    ``source`` est vide pour le dossier PDF ; pour un autre fichier, il donne le
    fichier et la ligne (par exemple « assessment_results.csv, ligne 12 »).
    """

    field: str
    question: str | None = None
    value: str | None = None
    source: str | None = None


class Finding(BaseModel):
    """Constat soumis à l'évaluateur. Ce n'est jamais une décision."""

    code: str
    severity: Severity
    message: str
    evidence: list[Evidence] = Field(default_factory=list)


def plain_text(text: str | None) -> str:
    """Forme comparable d'un texte : sans accents, sans casse, ponctuation réduite à des espaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def git_commit() -> str | None:
    """Commit courant du dépôt, pour dater un export de résultats (``None`` hors dépôt).

    Suffixe « -modifié » si des fichiers du dépôt diffèrent de ce commit ou n'y
    sont pas encore : le résultat ne vient alors pas exactement de ce commit.
    """
    folder = Path(__file__).parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=folder
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, cwd=folder
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip() or None
    if commit and status.stdout.strip():
        commit += "-modifié"
    return commit
