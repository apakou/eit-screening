"""Verdict proposé pour un dossier anonymisé.

1. Recherche des passages de chaque critère de la grille dans le dossier
   (étape 6), limitée au pseudonyme du candidat.
2. Le modèle de langage note chaque critère, donne une raison et recopie une
   citation ; il dit aussi si les réponses libres sont génériques. Il ne reçoit
   que du texte anonymisé : ni genre, ni âge, ni nationalité, ni numéro.
3. Le code vérifie chaque citation : si elle n'est pas mot pour mot dans le
   dossier, elle est signalée et ne compte pas comme preuve.
4. Une règle explicite (``verdict.toml``) combine notes, constats des étapes 1
   et 2 et citations pour proposer le verdict. L'évaluateur tranche.
"""

from __future__ import annotations

import re
from datetime import datetime

from ..grid import Grid
from ..privacy.anonymize import AnonymizedDossier
from ..screening.common import Finding
from ..search.retrieve import Hit
from .client import ChatClient, ChatResult
from .models import (
    ConcernResult,
    CriterionResult,
    DecisionRule,
    LlmCall,
    LlmCriterion,
    LlmGeneric,
    QuoteLocation,
    Verdict,
    VerdictConfig,
    VerdictLabel,
)

PROMPT_VERSION = "2026-11-22.1"

SYSTEM = """You help evaluators of a startup training program pre-screen applications.
You only see anonymised excerpts: [CANDIDAT] is the applicant, [PERSONNE_n] another person,
[PAYS], [VILLE], [LIEU], [LANGUE], [NATIONALITÉ] hide places, and [EMAIL], [TÉLÉPHONE], [LIEN] hide contacts.
Never guess what a mark hides. Judge only what the excerpts say.

For each criterion:
- give an integer score from 0 to its maximum, based only on the excerpts given for it;
- write one short sentence explaining the score;
- copy one quote that supports it, word for word from those excerpts (at most 30 words,
  no change, no ellipsis). If nothing supports a score above 0, use an empty quote.

Also say whether the free-text answers look generic: no personal fact, no number, no
concrete example, only broad statements. Copy one quote that shows it, or an empty quote.

Answer with JSON only, following the schema."""


def response_schema(grid: Grid) -> dict:
    """Schéma JSON imposé au modèle : un objet par critère, puis les réponses génériques."""
    criterion = {
        "type": "object",
        "properties": {"score": {"type": "integer"}, "reason": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["score", "reason", "quote"],
        "additionalProperties": False,
    }
    generic = {
        "type": "object",
        "properties": {"present": {"type": "boolean"}, "reason": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["present", "reason", "quote"],
        "additionalProperties": False,
    }
    properties = {c.key: criterion for c in grid.criteria}
    properties["generic_answers"] = generic
    return {
        "type": "object",
        "properties": properties,
        "required": [*(c.key for c in grid.criteria), "generic_answers"],
        "additionalProperties": False,
    }


def _passage_line(number: int, hit: Hit) -> str:
    p = hit.passage
    where = p.section
    if p.label:
        where += f", question: {p.label}"
    if p.page:
        where += f", page {p.page}"
    return f"[E{number}] ({where})\n{p.text}"


def build_full_dossier_messages(grid: Grid, dossier: AnonymizedDossier) -> list[dict]:
    """Variante de comparaison sans recherche : tout le dossier anonymisé, une fois, puis les critères.

    Les noms de fichiers ne sont pas envoyés, comme pour l'indexation.
    """
    lines = []
    for number, unit in enumerate((u for u in dossier.texts if u.section != "uploads"), start=1):
        where = unit.section + (f", question: {unit.label}" if unit.label else "") + (f", page {unit.page}" if unit.page else "")
        lines.append(f"[E{number}] ({where})\n{unit.text}")
    criteria = "\n".join(f'- {c.name} — key "{c.key}", maximum {c.max_points}' for c in grid.criteria)
    user = (
        "Criteria:\n" + criteria + "\n\nWhole application (all excerpts):\n\n" + "\n\n".join(lines)
        + "\n\nFor each criterion, use the excerpts relevant to it."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def build_messages(grid: Grid, evidence: dict[str, list[Hit]]) -> list[dict]:
    """Messages envoyés au modèle : consignes, puis critères et passages. Rien d'autre du dossier."""
    blocks = []
    number = 0
    for criterion in grid.criteria:
        lines = []
        for hit in evidence.get(criterion.key, []):
            number += 1
            lines.append(_passage_line(number, hit))
        excerpts = "\n\n".join(lines) or "(no excerpt found)"
        blocks.append(f"## {criterion.name} — key \"{criterion.key}\", maximum {criterion.max_points}\n\n{excerpts}")
    user = "Criteria and excerpts from one application:\n\n" + "\n\n".join(blocks)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------
# Vérification des citations
# --------------------------------------------------------------------------


def _normalize(text: str) -> tuple[str, list[int]]:
    """Espaces réduits à un seul, avec la position d'origine de chaque caractère."""
    out, origin, previous_space = [], [], False
    for index, char in enumerate(text):
        if char.isspace():
            if previous_space:
                continue
            out.append(" ")
            previous_space = True
        else:
            out.append(char)
            previous_space = False
        origin.append(index)
    return "".join(out), origin


def clean_quote(quote: str) -> str:
    """Retire les guillemets et espaces qui entourent une citation."""
    return quote.strip().strip("\"'“”‘’«»").strip()


def locate_quote(quote: str, dossier: AnonymizedDossier) -> QuoteLocation | None:
    """Emplacement de la citation dans le dossier anonymisé, mot pour mot (espaces près), ou None."""
    wanted = re.sub(r"\s+", " ", clean_quote(quote))
    if not wanted:
        return None
    for index, unit in enumerate(dossier.texts):
        normalized, origin = _normalize(unit.text)
        position = normalized.find(wanted)
        if position >= 0:
            start = origin[position]
            end = origin[position + len(wanted) - 1] + 1
            return QuoteLocation(
                unit_index=index, section=unit.section, label=unit.label, page=unit.page,
                start=unit.start, end=unit.end, char_start=start, char_end=end,
            )
    return None


# --------------------------------------------------------------------------
# Constats des étapes 1 et 2 et règle de décision
# --------------------------------------------------------------------------

ASSESSMENT_CONCERNS = {
    "assessment_not_found": "assessment_not_found",
    "assessment_late": "assessment_concerns",
    "assessment_too_fast": "assessment_concerns",
    "assessment_multiple_results": "assessment_concerns",
    "assessment_match_ambiguous": "assessment_concerns",
}


def concerns_from_findings(findings: list[Finding], grid: Grid) -> list[ConcernResult]:
    names = {c.key: c.name for c in grid.concerns}
    result = []
    for finding in findings:
        key = ASSESSMENT_CONCERNS.get(finding.code)
        if key and key in names:
            result.append(ConcernResult(key=key, name=names[key], source="contrôle", detail=finding.message))
    return result


def decide(
    total: int | None, findings: list[Finding], concerns: list[ConcernResult], unverified: int,
    schema_valid: bool, rule: DecisionRule,
) -> tuple[VerdictLabel, str]:
    """Règle explicite ; renvoie le verdict proposé et la raison de la règle appliquée."""
    alerts = [f for f in findings if f.severity == "alert"]
    if rule.review_on_alert and alerts:
        codes = ", ".join(sorted({f.code for f in alerts}))
        return "Request Final Review", f"Constat bloquant à examiner ({codes})."
    if not schema_valid or total is None:
        return "Request Final Review", "Le modèle n'a pas rendu de réponse conforme : aucune note à proposer."
    if unverified > rule.max_unverified_quotes:
        return "Request Final Review", f"{unverified} citation(s) introuvable(s) mot pour mot dans le dossier."
    if total >= rule.invite_min:
        if rule.review_invite_with_concern and concerns:
            keys = ", ".join(sorted({c.key for c in concerns}))
            return "Request Final Review", f"Total {total} suffisant pour l'entretien, mais Concern à examiner ({keys})."
        return "Interview Invitation", f"Total {total} ≥ {rule.invite_min}."
    if total >= rule.waitlist_min:
        return "Waitlist", f"Total {total} entre {rule.waitlist_min} et {rule.invite_min - 1}."
    return "Interview Reject", f"Total {total} < {rule.waitlist_min}."


def propose(
    dossier: AnonymizedDossier,
    evidence: dict[str, list[Hit]],
    grid: Grid,
    client: ChatClient,
    config: VerdictConfig,
    findings: list[Finding] | None = None,
    full_dossier: bool = False,
) -> tuple[Verdict, list[dict], ChatResult]:
    """Verdict proposé ; renvoie aussi les messages envoyés et la réponse brute, à journaliser.

    ``full_dossier`` : variante de comparaison, sans recherche (dossier entier dans le prompt).
    """
    findings = findings or []
    messages = build_full_dossier_messages(grid, dossier) if full_dossier else build_messages(grid, evidence)
    result = client.complete_json(messages, response_schema(grid), _Validator.for_grid(grid))
    criteria: list[CriterionResult] = []
    concerns = concerns_from_findings(findings, grid)
    total = None
    if result.content is not None:
        total = 0
        for criterion in grid.criteria:
            answer = LlmCriterion.model_validate(result.content[criterion.key])
            score = max(0, min(criterion.max_points, answer.score))
            location = locate_quote(answer.quote, dossier)
            criteria.append(
                CriterionResult(
                    key=criterion.key, name=criterion.name, max_points=criterion.max_points, score=score,
                    reason=answer.reason.strip(), quote=clean_quote(answer.quote),
                    quote_verified=location is not None, quote_location=location,
                    passage_ids=[h.passage.id for h in evidence.get(criterion.key, [])],
                )
            )
            total += score
        generic = LlmGeneric.model_validate(result.content["generic_answers"])
        names = {c.key: c.name for c in grid.concerns}
        if generic.present and "generic_ai_responses" in names:
            location = locate_quote(generic.quote, dossier) if generic.quote.strip() else None
            concerns.append(
                ConcernResult(
                    key="generic_ai_responses", name=names["generic_ai_responses"], source="modèle",
                    detail=generic.reason.strip(), quote=clean_quote(generic.quote) or None,
                    quote_verified=None if not generic.quote.strip() else location is not None,
                )
            )
    quoted = [c for c in criteria if c.quote]
    unverified = sum(not c.quote_verified for c in quoted)
    proposed, rule = decide(total, findings, concerns, unverified, result.content is not None, config.decision)
    verdict = Verdict(
        pseudonym=dossier.pseudonym,
        proposed=proposed,
        rule=rule,
        total=total,
        max_total=grid.total_points,
        criteria=criteria,
        concerns=concerns,
        findings=findings,
        quotes_verified=sum(c.quote_verified for c in quoted),
        quotes_total=len(quoted),
        llm=LlmCall(
            model=config.llm.model, base_url=config.llm.base_url, attempts=result.attempts,
            seconds=result.seconds, schema_valid=result.content is not None, errors=result.errors,
        ),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return verdict, messages, result


class _Validator:
    """Valide la réponse : un objet par critère et l'avis sur les réponses génériques."""

    @staticmethod
    def for_grid(grid: Grid):
        from pydantic import create_model

        fields = {c.key: (LlmCriterion, ...) for c in grid.criteria}
        fields["generic_answers"] = (LlmGeneric, ...)
        return create_model("LlmVerdict", **fields)
