"""Recherche hybride et re-ranking : mesures, isolement des dossiers, grille, modèles réels."""

import pytest

from eit_screening.grid import Grid, load_grid
from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata
from eit_screening.search.chunking import Passage, chunk_dossier
from eit_screening.search.config import load_config
from eit_screening.search.embed import BgeM3, Embedding
from eit_screening.search.evaluate import (
    Rule,
    evaluate,
    first_relevant_rank,
    load_questions,
    random_hit_at_k,
)
from eit_screening.search.index import index_dossiers
from eit_screening.search.rerank import Reranker
from eit_screening.search.retrieve import MODES, Hit, Retriever
from eit_screening.search.store import PassageStore, open_client

CONFIG = load_config()
VOCABULARY = ["drone", "farm", "lead", "team", "test", "hard", "degree", "university", "money", "app"]


class KeywordEmbedder:
    """Encodeur de test : un axe par mot du vocabulaire, poids lexicaux sur les mêmes mots."""

    name = "mots-clés"

    def encode(self, texts):
        result = []
        for text in texts:
            words = text.lower().split()
            dense = [float(sum(w.startswith(v) for w in words)) + 0.01 for v in VOCABULARY]
            norm = sum(x * x for x in dense) ** 0.5
            sparse = {i: 1.0 for i, v in enumerate(VOCABULARY) if any(w.startswith(v) for w in words)}
            result.append(Embedding(dense=[x / norm for x in dense], sparse=sparse, tokens=len(words), truncated=False))
        return result


class KeywordReranker:
    name = "mots-clés"

    def score(self, query, passages):
        wanted = {w for w in query.lower().split() if any(w.startswith(v) for v in VOCABULARY)}
        return [float(sum(any(w.startswith(q[:4]) for q in wanted) for w in p.lower().split())) for p in passages]


def _dossier(pseudonym, essays):
    return AnonymizedDossier(
        pseudonym=pseudonym,
        metadata=Metadata(),
        texts=[AnonymizedText(section="essay", label=label, text=text) for label, text in essays],
    )


DOSSIERS = [
    _dossier("C-0000000A", [
        ("Build", "I would build a drone to watch farm fields."),
        ("Lead", "I had to lead my team when the test was hard."),
        ("Study", "I hold a degree from a university in computing."),
    ]),
    _dossier("C-0000000B", [
        ("Build", "A mobile money app for traders."),
        ("Lead", "I lead a team of volunteers."),
    ]),
]


@pytest.fixture()
def retriever():
    store = PassageStore(open_client(CONFIG.qdrant, path=":memory:"), "passages")
    index_dossiers(DOSSIERS, store, KeywordEmbedder(), CONFIG)
    return Retriever(store, KeywordEmbedder(), CONFIG, KeywordReranker())


# --- Recherche ------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_search_stays_in_the_candidate_dossier(retriever, mode):
    for pseudonym in ("C-0000000A", "C-0000000B"):
        (hits,) = retriever.search_many(pseudonym, ["lead a team"], mode=mode, top_k=5)
        assert hits and {h.passage.pseudonym for h in hits} == {pseudonym}


def test_hybrid_and_rerank_find_the_right_passage(retriever):
    for mode in MODES:
        (hits,) = retriever.search_many("C-0000000A", ["drone for a farm"], mode=mode, top_k=1)
        assert hits[0].passage.label == "Build", mode


def test_rerank_reorders_candidates(retriever):
    (fused,) = retriever.search_many("C-0000000A", ["degree university"], mode="hybrid", top_k=3)
    reranked = retriever.rerank("degree university", fused, top_k=3)
    assert reranked[0].passage.label == "Study"
    assert reranked[0].score >= reranked[-1].score


def test_rerank_needs_a_model(retriever):
    retriever.reranker = None
    with pytest.raises(ValueError):
        retriever.search_many("C-0000000A", ["drone"], mode="hybrid_rerank")


def test_default_chain_comes_from_configuration(retriever):
    assert CONFIG.retrieval.mode == "dense" and retriever.default_mode == "dense"
    config = CONFIG.model_copy(deep=True)
    config.retrieval.mode = "hybrid_rerank"
    retriever.config = config
    assert retriever.default_mode == "hybrid_rerank"
    config.reranking.enabled = False  # re-ranking désactivé : retour à l'hybride
    assert retriever.default_mode == "hybrid"
    (hits,) = retriever.search_many("C-0000000A", ["drone farm"])
    assert hits[0].passage.label == "Build"


def test_ties_come_back_in_a_stable_order(retriever):
    (query,) = retriever.encode(["lead"])
    runs = {tuple(h.passage.id for h in retriever.candidates("C-0000000A", query, "hybrid", 3)) for _ in range(5)}
    assert len(runs) == 1


def test_one_query_per_criterion(retriever):
    grid = load_grid()
    found = retriever.for_criteria("C-0000000A", grid, top_k=2)
    assert list(found) == [c.key for c in grid.criteria]
    assert all(len(hits) <= 2 and all(h.passage.pseudonym == "C-0000000A" for h in hits) for hits in found.values())


# --- Mesures ------------------------------------------------------------------


def _hit(passage_id):
    return Hit(
        passage=Passage(id=passage_id, pseudonym="C", section="essay", unit_start=0, unit_end=0,
                        char_start=0, char_end=1, text="x"),
        score=0.0,
    )


def test_first_relevant_rank():
    hits = [_hit("a"), _hit("b"), _hit("c")]
    assert first_relevant_rank(hits, {"c"}) == 3
    assert first_relevant_rank(hits, {"b", "c"}) == 2
    assert first_relevant_rank(hits, {"z"}) is None


def test_random_baseline():
    assert random_hit_at_k(12, 1) == pytest.approx(0.25)
    assert random_hit_at_k(3, 1) == 1.0
    assert random_hit_at_k(10, 2) == pytest.approx(1 - 56 / 120)


def test_relevance_rules():
    passage = Passage(id="1", pseudonym="C", section="attachment", page=16, unit_start=0, unit_end=0,
                      char_start=0, char_end=10, text="This certificate is presented to [CANDIDAT]")
    assert Rule(section="attachment", text_contains="PRESENTED TO").matches(passage)
    assert not Rule(section="attachment", text_contains="EDUCATION").matches(passage)
    assert not Rule(section="essay").matches(passage)
    assert not Rule(section="attachment", label_contains="anything").matches(passage)


def test_evaluate_with_known_ranks(retriever):
    from eit_screening.search.evaluate import Question

    questions = [
        Question(key="build", text="drone farm app", relevant=[Rule(section="essay", label_contains="Build")]),
        Question(key="leadership", text="lead team", relevant=[Rule(section="essay", label_contains="Lead")]),
        Question(key="none", text="drone", relevant=[Rule(section="experience")]),
    ]
    result = evaluate(retriever.store, retriever, questions, ["C-0000000A", "C-0000000B"], release_embedder=False)
    assert result.per_question_count == {"build": 2, "leadership": 2, "none": 0}
    assert result.queries == 4
    for mode in MODES:
        assert result.modes[mode].hit_at_3 == 1.0
    assert result.candidates_recall == 1.0 and result.failures == []


def test_question_set():
    questions = load_questions()
    assert len(questions) == 10 and len({q.key for q in questions}) == 10
    assert {"build", "unconventional", "leadership", "success", "perseverance"} <= {q.key for q in questions}


def test_grid_from_configuration(tmp_path):
    grid = load_grid()
    assert grid.total_points == 40 and len(grid.criteria) == 4
    assert {c.name for c in grid.criteria} >= {"Resume & Technical Experience", "Program Fit & Collaboration"}
    with pytest.raises(ValueError):
        Grid(total_points=30, criteria=[c.model_dump() for c in grid.criteria])


# --- Modèles réels ---------------------------------------------------------------


def test_reranker_matches_model_card():
    reranker = Reranker(CONFIG.reranking)
    panda = "The giant panda (Ailuropoda melanoleuca), sometimes called a panda bear or simply panda, " \
            "is a bear species endemic to China."
    scores = reranker.score("what is panda?", ["hi", panda])
    assert scores == pytest.approx([-8.1875, 5.26171875], abs=0.02)
    assert reranker.score("query", ["passage"])[0] == pytest.approx(-5.65234375, abs=0.02)


def test_real_chain_on_one_dossier(anonymized_cohort):
    dossier = anonymized_cohort[0]
    store = PassageStore(open_client(CONFIG.qdrant, path=":memory:"), "passages")
    index_dossiers([dossier], store, BgeM3(CONFIG.embedding), CONFIG)
    retriever = Retriever(store, BgeM3(CONFIG.embedding), CONFIG, Reranker(CONFIG.reranking))
    questions = load_questions()
    result = evaluate(store, retriever, questions, [dossier.pseudonym])
    assert result.queries >= 9
    assert result.candidates_recall >= 0.9
    assert result.modes["hybrid_rerank"].hit_at_3 >= 0.7
    passages = chunk_dossier(dossier, CONFIG.chunking)
    assert {p.id for p in store.passages()} == {p.id for p in passages}
