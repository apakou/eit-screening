"""Découpage et indexation : emplacement exact de chaque passage, horodatage, embeddings bge-m3."""

import re

import pytest

from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata
from eit_screening.search.chunking import chunk_dossier, passage_text
from eit_screening.search.config import ChunkingRule, load_config
from eit_screening.search.embed import BgeM3, Embedding, lexical_score
from eit_screening.search.index import check_locations, index_dossiers, read_dossiers
from eit_screening.search.store import PassageStore, open_client

CONFIG = load_config()


class FakeEmbedder:
    """Encodeur de test : vecteurs déterministes, sans modèle."""

    name = "fake"

    def encode(self, texts):
        return [
            Embedding(
                dense=[1.0, float(len(text) % 7), 0.5],
                sparse={sum(map(ord, word)) % 997: 1.0 for word in text.split()[:8]},
                tokens=len(text.split()),
                truncated=False,
            )
            for text in texts
        ]


def _store(tmp_path=None):
    client = open_client(CONFIG.qdrant, path=str(tmp_path / "qdrant") if tmp_path else ":memory:")
    return PassageStore(client, "passages")


# --- Critère d'acceptation -----------------------------------------------------


def test_every_indexed_passage_points_to_its_exact_place(anonymized_cohort, tmp_path):
    """Chaque passage relu dans Qdrant redonne exactement son texte, sa section, sa page et son horodatage."""
    store = _store(tmp_path)
    report = index_dossiers(anonymized_cohort, store, FakeEmbedder(), CONFIG)
    check = check_locations(store, anonymized_cohort, CONFIG.chunking.sections)
    assert report.passages == check.passages == store.count() > 0
    assert check.located == check.passages
    assert check.mismatches == [] and check.uncovered_units == []
    assert set(report.by_section) == set(CONFIG.chunking.sections)


def test_location_check_catches_errors(anonymized_cohort):
    """Le contrôle échoue bien : point supprimé, texte modifié, question changée."""
    from qdrant_client import models

    dossier = anonymized_cohort[0]
    store = _store()
    index_dossiers([dossier], store, FakeEmbedder(), CONFIG)
    passages = store.passages()
    store.client.delete("passages", points_selector=models.PointIdsList(points=[passages[0].id]))
    check = check_locations(store, [dossier], CONFIG.chunking.sections)
    assert check.uncovered_units and check.mismatches == []

    index_dossiers([dossier], store, FakeEmbedder(), CONFIG)
    altered = dossier.model_copy(deep=True)
    essay = next(t for t in altered.texts if t.section == "essay")
    essay.text = "X" + essay.text[1:]
    assert len(check_locations(store, [altered], CONFIG.chunking.sections).mismatches) == 1

    relabelled = dossier.model_copy(deep=True)
    next(t for t in relabelled.texts if t.section == "essay").label = "Autre question"
    assert len(check_locations(store, [relabelled], CONFIG.chunking.sections).mismatches) == 1


def test_empty_first_dossier():
    store = _store()
    empty = _dossier([AnonymizedText(section="uploads", text="CV.pdf")])
    report = index_dossiers([empty], store, FakeEmbedder(), CONFIG)
    assert report.passages == 0


def test_payload_holds_no_application_number(anonymized_cohort, cohort):
    _, dossiers = cohort
    store = _store()
    index_dossiers(anonymized_cohort[:3], store, FakeEmbedder(), CONFIG)
    numbers = {d.application.application_id for d in dossiers}
    points, _ = store.client.scroll("passages", limit=1000, with_payload=True)
    for point in points:
        assert not numbers & {str(value) for value in point.payload.values()}
        assert re.fullmatch(r"C-[0-9A-F]{8}", point.payload["pseudonym"])


def test_reindexing_replaces_a_dossier(anonymized_cohort):
    store = _store()
    dossier = anonymized_cohort[0]
    index_dossiers([dossier], store, FakeEmbedder(), CONFIG)
    first = sorted(p.id for p in store.passages())
    index_dossiers([dossier], store, FakeEmbedder(), CONFIG)
    assert sorted(p.id for p in store.passages()) == first  # mêmes identifiants, pas de doublons
    shorter = dossier.model_copy(update={"texts": dossier.texts[:2]})
    index_dossiers([shorter], store, FakeEmbedder(), CONFIG)
    assert store.count() == len(chunk_dossier(shorter, CONFIG.chunking)) < len(first)


def test_read_dossiers_skips_summary(tmp_path, anonymized_cohort):
    dossier = anonymized_cohort[0]
    (tmp_path / f"{dossier.pseudonym}.json").write_text(dossier.model_dump_json(), encoding="utf-8")
    (tmp_path / "_resume.json").write_text("{}", encoding="utf-8")
    assert [d.pseudonym for d in read_dossiers(tmp_path)] == [dossier.pseudonym]


# --- Découpage ---------------------------------------------------------------


def _dossier(texts):
    return AnonymizedDossier(pseudonym="C-00000001", metadata=Metadata(), texts=texts)


def test_long_text_is_split_with_overlap():
    words = [f"mot{i}" for i in range(300)]
    dossier = _dossier([AnonymizedText(section="attachment", page=15, text="  " + "  ".join(words) + "\n")])
    rule = ChunkingRule(max_words=120, overlap_words=20, sections=["attachment"])
    passages = chunk_dossier(dossier, rule)
    assert [len(p.text.split()) for p in passages] == [120, 120, 100]
    assert passages[0].text.split()[-20:] == passages[1].text.split()[:20]
    for passage in passages:
        assert passage_text(passage, dossier) == passage.text and passage.page == 15


def test_timestamped_segments_are_grouped_and_keep_their_times():
    segments = [
        AnonymizedText(section="personal_statement", start=i * 4.0, end=i * 4.0 + 3.5, text=f"Phrase {i} " + "mot " * 9)
        for i in range(5)
    ]
    dossier = _dossier([AnonymizedText(section="essay", label="Q1", text="Une réponse."), *segments])
    rule = ChunkingRule(max_words=25, overlap_words=0, sections=["essay", "personal_statement"])
    passages = chunk_dossier(dossier, rule)
    spoken = [p for p in passages if p.section == "personal_statement"]
    assert [(p.unit_start, p.unit_end, p.start, p.end) for p in spoken] == [
        (1, 2, 0.0, 7.5), (3, 4, 8.0, 15.5), (5, 5, 16.0, 19.5),
    ]
    for passage in passages:
        assert passage_text(passage, dossier) == passage.text
    store = _store()
    store.ensure(3)
    store.replace_dossier(dossier.pseudonym, passages, FakeEmbedder().encode([p.text for p in passages]), "fake")
    check = check_locations(store, [dossier], rule.sections)
    assert check.located == len(passages) and check.uncovered_units == []


def test_text_transcript_without_times_is_split_normally():
    dossier = _dossier([AnonymizedText(section="personal_statement", text="Hello, I am [CANDIDAT].")])
    (passage,) = chunk_dossier(dossier, CONFIG.chunking)
    assert (passage.start, passage.end, passage.text) == (None, None, "Hello, I am [CANDIDAT].")


def test_uploads_are_not_indexed():
    dossier = _dossier([AnonymizedText(section="uploads", text="CV.pdf")])
    assert chunk_dossier(dossier, CONFIG.chunking) == []


def test_invalid_overlap():
    with pytest.raises(ValueError):
        ChunkingRule(max_words=50, overlap_words=50, sections=[])


# --- bge-m3 ------------------------------------------------------------------


@pytest.fixture(scope="module")
def bge():
    return BgeM3(CONFIG.embedding)


def test_bge_m3_matches_model_card(bge):
    """Valeurs publiées dans la fiche du modèle (calculées en demi-précision : tolérance 0,002)."""
    queries = ["What is BGE M3?", "Defination of BM25"]
    documents = [
        "BGE M3 is an embedding model supporting dense retrieval, lexical matching and multi-vector interaction.",
        "BM25 is a bag-of-words retrieval function that ranks a set of documents based on the query terms "
        "appearing in each document",
    ]
    q, d = bge.encode(queries), bge.encode(documents)
    expected = [[0.6265, 0.3477], [0.3499, 0.678]]
    for i in range(2):
        for j in range(2):
            got = sum(a * b for a, b in zip(q[i].dense, d[j].dense))
            assert got == pytest.approx(expected[i][j], abs=0.002)
    reference = {"What": 0.08356, "is": 0.0814, "B": 0.1296, "GE": 0.252, "M": 0.1702, "3": 0.2695, "?": 0.04092}
    tokens = bge.lexical_tokens(q[0].sparse)
    assert set(tokens) == set(reference)
    for token, weight in reference.items():
        assert tokens[token] == pytest.approx(weight, abs=0.002)
    assert lexical_score(q[0].sparse, d[0].sparse) == pytest.approx(0.1955, abs=0.002)
    assert lexical_score(q[0].sparse, q[1].sparse) == 0


def test_truncation_is_counted():
    rule = CONFIG.embedding.model_copy(update={"max_tokens": 16})
    (embedding,) = BgeM3(rule).encode(["word " * 60])
    assert embedding.truncated and embedding.tokens > 16


def test_real_embeddings_in_qdrant(anonymized_cohort, bge):
    store = _store()
    dossier = anonymized_cohort[0]
    report = index_dossiers([dossier], store, bge, CONFIG)
    assert store.count() == report.passages > 0 and report.truncated == 0
    check = check_locations(store, [dossier], CONFIG.chunking.sections)
    assert check.located == check.passages
