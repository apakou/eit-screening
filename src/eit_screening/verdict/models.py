"""Modèles du verdict : configuration, sortie du modèle de langage, verdict proposé."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..screening.common import Finding

# Guide 2027 : trois décisions, et un booléen distinct pour la revue complémentaire.
VerdictLabel = Literal["Interview Invitation", "Interview Reject", "Waitlist"]


class LlmRule(BaseModel):
    base_url: str
    model: str
    api_key_env: str = "EIT_LLM_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 1200
    timeout_seconds: float = 600
    max_attempts: int = 3


class RetrievalRule(BaseModel):
    passages_per_criterion: int = 3


class DecisionRule(BaseModel):
    invite_min: int
    waitlist_min: int
    exclusion_codes: list[str] = Field(default_factory=list)
    review_on_findings: bool = True
    review_on_concerns: bool = True
    max_unverified_quotes: int = 0


class VerdictConfig(BaseModel):
    llm: LlmRule
    retrieval: RetrievalRule = Field(default_factory=RetrievalRule)
    decision: DecisionRule


def load_config(path: Path | str | None = None) -> VerdictConfig:
    if path is None:
        raw = resources.files(__package__).joinpath("verdict.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return VerdictConfig.model_validate(tomllib.loads(raw.decode("utf-8")))


# --- Sortie attendue du modèle (vérifiée contre ce schéma) -------------------------


class LlmCriterion(BaseModel):
    score: int
    reason: str
    quote: str


class LlmGeneric(BaseModel):
    present: bool
    reason: str
    quote: str


# --- Verdict proposé -------------------------------------------------------------


class QuoteLocation(BaseModel):
    unit_index: int
    section: str
    label: str | None = None
    page: int | None = None
    start: float | None = None
    end: float | None = None
    char_start: int
    char_end: int


class CriterionResult(BaseModel):
    key: str
    name: str
    max_points: int
    score: int
    reason: str
    quote: str
    quote_verified: bool
    quote_location: QuoteLocation | None = None
    passage_ids: list[str] = Field(default_factory=list)


class ConcernResult(BaseModel):
    key: str
    name: str
    source: Literal["contrôle", "modèle"]
    detail: str
    quote: str | None = None
    quote_verified: bool | None = None


class LlmCall(BaseModel):
    model: str
    base_url: str
    attempts: int
    seconds: float
    schema_valid: bool
    errors: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """Verdict proposé à l'évaluateur. Il ne décide de rien : l'évaluateur valide ou modifie."""

    pseudonym: str
    proposed: VerdictLabel | None  # None : aucune note exploitable, rien à proposer
    request_further_review: bool
    rule: str  # pourquoi cette décision, en une phrase
    review_reasons: list[str] = Field(default_factory=list)
    total: int | None = None
    max_total: int
    criteria: list[CriterionResult] = Field(default_factory=list)
    concerns: list[ConcernResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    quotes_verified: int = 0
    quotes_total: int = 0
    llm: LlmCall
    created_at: str
