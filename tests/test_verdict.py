"""Verdict proposé : schéma, nouvelles tentatives, citations vérifiées, règle de décision, contenu du prompt."""

import json

import httpx
import pytest

from eit_screening.grid import load_grid
from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata
from eit_screening.screening.common import Finding
from eit_screening.search.chunking import Passage
from eit_screening.search.retrieve import Hit
from eit_screening.verdict.client import ChatClient
from eit_screening.verdict.models import load_config
from eit_screening.verdict.propose import (
    ConcernResult,
    build_messages,
    decide,
    locate_quote,
    propose,
    response_schema,
)

GRID = load_grid()
CONFIG = load_config()

DOSSIER = AnonymizedDossier(
    pseudonym="C-0000ABCD",
    metadata=Metadata(gender="Female", age=27, citizenship="Togo"),
    texts=[
        AnonymizedText(section="essay", label="Q1", text="I would build speech recognition for [LANGUE]\nand other languages."),
        AnonymizedText(section="attachment", page=16, text="[CANDIDAT]\nFull Stack Developer\nSKILLS\nPython and Django"),
        AnonymizedText(section="personal_statement", start=0.0, end=4.2, text="Hello, my name is [CANDIDAT]."),
    ],
)


def _hit(unit: int, text: str) -> Hit:
    return Hit(
        passage=Passage(id=f"p{unit}", pseudonym=DOSSIER.pseudonym, section=DOSSIER.texts[unit].section,
                        label=DOSSIER.texts[unit].label, page=DOSSIER.texts[unit].page, unit_start=unit,
                        unit_end=unit, char_start=0, char_end=len(text), text=text),
        score=1.0,
    )


EVIDENCE = {c.key: [_hit(0, DOSSIER.texts[0].text), _hit(1, DOSSIER.texts[1].text)] for c in GRID.criteria}


def _answer(scores=(8, 8, 7, 7), quote="Python and Django", generic=False):
    content = {
        c.key: {"score": s, "reason": "Raison.", "quote": quote} for c, s in zip(GRID.criteria, scores)
    }
    content["generic_answers"] = {"present": generic, "reason": "Réponses vagues." if generic else "", "quote": ""}
    return content


def _client(*replies):
    """Faux serveur compatible OpenAI : renvoie les réponses données, dans l'ordre."""
    seen = []
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        reply = queue.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})

    return ChatClient(CONFIG.llm, transport=httpx.MockTransport(handler)), seen


# --- Citations ------------------------------------------------------------------


def test_quote_found_word_for_word_despite_line_breaks():
    location = locate_quote("speech recognition for [LANGUE] and other", DOSSIER)
    assert location is not None and location.unit_index == 0 and location.section == "essay"
    text = DOSSIER.texts[0].text
    assert text[location.char_start:location.char_end] == "speech recognition for [LANGUE]\nand other"


def test_quote_with_quotation_marks_and_timestamps():
    location = locate_quote("« Hello, my name is [CANDIDAT]. »", DOSSIER)
    assert location is not None and (location.start, location.end) == (0.0, 4.2)


@pytest.mark.parametrize("quote", ["speech recognition for Swahili", "Python & Django", "", "   "])
def test_altered_or_empty_quotes_are_not_found(quote):
    assert locate_quote(quote, DOSSIER) is None


# --- Appel au modèle ------------------------------------------------------------


def test_verdict_with_verified_quotes():
    client, seen = _client(_answer())
    verdict, messages, result = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert verdict.llm.schema_valid and verdict.llm.attempts == 1
    assert verdict.total == 30 and verdict.proposed == "Interview Invitation"
    assert verdict.quotes_verified == verdict.quotes_total == 4
    assert verdict.criteria[0].quote_location.page == 16
    body = seen[0]
    assert body["model"] == CONFIG.llm.model and body["response_format"]["type"] == "json_schema"


def test_invalid_answers_are_retried():
    client, seen = _client("pas du JSON", {"resume_technical": {"score": 5}}, _answer())
    verdict, _, result = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert verdict.llm.schema_valid and verdict.llm.attempts == 3 and len(result.errors) == 2


def test_no_valid_answer_means_review():
    client, _ = _client("x", "y", "z")
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert not verdict.llm.schema_valid and verdict.total is None
    assert verdict.proposed is None and verdict.request_further_review


def test_invented_quote_is_flagged_and_blocks_the_proposal():
    client, _ = _client(_answer(quote="I led a team of fifty engineers at Google."))
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert verdict.quotes_verified == 0 and verdict.quotes_total == 4
    assert not any(c.quote_verified for c in verdict.criteria)
    # La décision suit les notes, mais la revue complémentaire est demandée.
    assert verdict.proposed == "Interview Invitation" and verdict.request_further_review
    assert any("introuvable" in r for r in verdict.review_reasons)


def test_scores_are_clamped_to_the_grid():
    client, _ = _client(_answer(scores=(15, -2, 10, 10)))
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert [c.score for c in verdict.criteria] == [10, 0, 10, 10]


def test_generic_answers_become_a_concern():
    client, _ = _client(_answer(generic=True))
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG)
    assert [c.key for c in verdict.concerns] == ["generic_ai_responses"]
    assert verdict.proposed == "Interview Invitation" and verdict.request_further_review


def test_findings_from_earlier_steps():
    late = Finding(code="assessment_late", severity="to_check", message="Test soumis après le 20 juillet.")
    client, _ = _client(_answer())
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG, findings=[late])
    assert verdict.proposed == "Interview Invitation" and verdict.request_further_review
    assert any("assessment_late" in r for r in verdict.review_reasons)
    assert [c.key for c in verdict.concerns] == ["assessment_concerns"]


@pytest.mark.parametrize("code", ["age_out_of_range", "citizenship_outside_region", "graduation_after_cutoff"])
def test_guide_exclusions_propose_a_reject(code):
    excluded = Finding(code=code, severity="alert", message="Écarté par le guide.")
    client, _ = _client(_answer())
    verdict, _, _ = propose(DOSSIER, EVIDENCE, GRID, client, CONFIG, findings=[excluded])
    assert verdict.proposed == "Interview Reject" and code in verdict.rule
    assert verdict.total == 30  # les notes restent affichées


# --- Règle de décision ------------------------------------------------------------

RULE = CONFIG.decision


@pytest.mark.parametrize(
    ("total", "expected"),
    [(40, "Interview Invitation"), (RULE.invite_min, "Interview Invitation"), (RULE.invite_min - 1, "Waitlist"),
     (RULE.waitlist_min, "Waitlist"), (RULE.waitlist_min - 1, "Interview Reject"), (0, "Interview Reject")],
)
def test_thresholds(total, expected):
    decision = decide(total, [], [], 0, True, RULE)
    assert decision.proposed == expected and not decision.request_further_review


def test_flagged_findings_ask_for_review_without_changing_the_decision():
    for code in ("age_borderline", "graduation_review", "assessment_late", "eligibility_answer_no"):
        note = Finding(code=code, severity="to_check", message="Signalé.")
        decision = decide(35, [note], [], 0, True, RULE)
        assert decision.proposed == "Interview Invitation" and decision.request_further_review, code


def test_dual_citizenship_is_not_an_exclusion():
    dual = Finding(code="citizenship_outside_region", severity="to_check", message="Double nationalité.")
    decision = decide(35, [dual], [], 0, True, RULE)
    assert decision.proposed == "Interview Invitation" and decision.request_further_review


def test_concern_asks_for_review():
    concern = ConcernResult(key="assessment_concerns", name="Assessment concerns", source="contrôle", detail="x")
    assert decide(35, [], [concern], 0, True, RULE)[:2] == ("Interview Invitation", True)
    assert decide(10, [], [concern], 0, True, RULE)[:2] == ("Interview Reject", True)


def test_only_three_decisions():
    from typing import get_args

    from eit_screening.verdict.models import VerdictLabel

    assert set(get_args(VerdictLabel)) == {"Interview Invitation", "Interview Reject", "Waitlist"}


# --- Ce qui part vers le modèle -------------------------------------------------------


def test_prompt_holds_only_anonymised_excerpts():
    messages = build_messages(GRID, EVIDENCE)
    text = "\n".join(m["content"] for m in messages)
    for secret in ("Female", "27", "Togo", DOSSIER.pseudonym):
        assert secret not in text
    for criterion in GRID.criteria:
        assert f'"{criterion.key}"' in text and criterion.name in text
    assert "Python and Django" in text


def test_schema_lists_every_criterion():
    schema = response_schema(GRID)
    assert schema["required"] == [c.key for c in GRID.criteria] + ["generic_answers"]


def test_full_dossier_variant_sends_every_text_but_no_file_names():
    from eit_screening.verdict.propose import build_full_dossier_messages

    dossier = DOSSIER.model_copy(update={"texts": [*DOSSIER.texts, AnonymizedText(section="uploads", text="CV.pdf")]})
    text = build_full_dossier_messages(GRID, dossier)[1]["content"]
    assert all(unit.text in text for unit in DOSSIER.texts) and "CV.pdf" not in text
    client, seen = _client(_answer())
    verdict, _, _ = propose(dossier, {}, GRID, client, CONFIG, full_dossier=True)
    assert verdict.llm.schema_valid and verdict.criteria[0].passage_ids == []
