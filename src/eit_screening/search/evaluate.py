"""Mesure de la recherche sur un jeu de questions dont la réponse est connue par construction.

Pour chaque dossier indexé et chaque question de ``questions.toml``, la
question est posée dans le seul dossier du candidat. Les passages pertinents
se déduisent de la structure du dossier (section, question du formulaire,
contenu de la page). Quatre chaînes sont comparées : dense, lexicale,
hybride (fusion RRF) et hybride suivie du re-ranking.

Mesures : succès au rang 1 et dans les 3 premiers, rang réciproque moyen,
rappel des candidats transmis au re-ranking, et succès attendu d'un tirage au
hasard dans les 3 premiers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
from collections import defaultdict
from datetime import datetime
from importlib import resources
from math import comb
from pathlib import Path

from pydantic import BaseModel, Field

from .. import __version__
from ..grid import load_grid
from ..screening.common import git_commit
from .chunking import Passage
from .config import SearchConfig, load_config
from .embed import BgeM3
from .rerank import Reranker
from .retrieve import MODES, Hit, Retriever
from .store import PassageStore, open_client

STRICT = {"build", "unconventional", "leadership", "success", "perseverance"}


class Rule(BaseModel):
    section: str
    label_contains: str | None = None
    text_contains: str | None = None

    def matches(self, passage: Passage) -> bool:
        if passage.section != self.section:
            return False
        if self.label_contains and self.label_contains.casefold() not in (passage.label or "").casefold():
            return False
        if self.text_contains and self.text_contains.casefold() not in passage.text.casefold():
            return False
        return True


class Question(BaseModel):
    key: str
    text: str
    relevant: list[Rule]

    def relevant_ids(self, passages: list[Passage]) -> set[str]:
        return {p.id for p in passages if any(rule.matches(p) for rule in self.relevant)}


def load_questions(path: Path | str | None = None) -> list[Question]:
    if path is None:
        raw = resources.files(__package__).joinpath("questions.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return [Question.model_validate(q) for q in tomllib.loads(raw.decode("utf-8"))["question"]]


class QueryResult(BaseModel):
    pseudonym: str
    question: str
    passages_in_dossier: int
    relevant: int
    random_hit_at_3: float
    ranks: dict[str, int | None]  # rang du premier passage pertinent, par chaîne (None : absent)
    candidates_recall: bool  # un passage pertinent figure parmi les candidats du re-ranking


class ModeScore(BaseModel):
    queries: int
    hit_at_1: float
    hit_at_3: float
    mrr: float


class Evaluation(BaseModel):
    dossiers: int
    queries: int
    per_question_count: dict[str, int]
    modes: dict[str, ModeScore]
    strict_modes: dict[str, ModeScore]
    per_question_hit_at_3: dict[str, dict[str, float]]
    random_hit_at_3: float
    random_hit_at_3_strict: float
    random_per_question: dict[str, float]
    candidates_recall: float
    failures: list[str] = Field(default_factory=list)
    results: list[QueryResult] = Field(default_factory=list)


def first_relevant_rank(hits: list[Hit], relevant: set[str]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit.passage.id in relevant:
            return rank
    return None


def random_hit_at_k(total: int, relevant: int, k: int = 3) -> float:
    """Probabilité qu'un tirage au hasard de k passages contienne un passage pertinent."""
    k = min(k, total)
    return 1 - comb(total - relevant, k) / comb(total, k) if total else 0.0


def _score(results: list[QueryResult], mode: str) -> ModeScore:
    ranks = [r.ranks[mode] for r in results]
    count = len(ranks) or 1
    return ModeScore(
        queries=len(ranks),
        hit_at_1=round(sum(r == 1 for r in ranks) / count, 4),
        hit_at_3=round(sum(r is not None and r <= 3 for r in ranks) / count, 4),
        mrr=round(sum(1 / r for r in ranks if r) / count, 4),
    )


def evaluate(
    store: PassageStore, retriever: Retriever, questions: list[Question], pseudonyms: list[str],
    modes: tuple[str, ...] = MODES, release_embedder: bool = True,
) -> Evaluation:
    """Pose chaque question dans chaque dossier et compare les chaînes de recherche."""
    candidates_limit = retriever.config.retrieval.candidates
    encoded = retriever.encode([q.text for q in questions], release_embedder=release_embedder and "hybrid_rerank" in modes)
    results: list[QueryResult] = []
    for pseudonym in pseudonyms:
        passages = store.passages(pseudonym)
        for question, query in zip(questions, encoded):
            relevant = question.relevant_ids(passages)
            if not relevant:
                continue
            ranks: dict[str, int | None] = {}
            fused: list[Hit] = []
            for mode in modes:
                if mode == "hybrid_rerank":
                    reranked = retriever.rerank(question.text, fused, top_k=candidates_limit)
                    ranks[mode] = first_relevant_rank(reranked, relevant)
                    continue
                hits = retriever.candidates(pseudonym, query, mode, candidates_limit)
                if mode == "hybrid":
                    fused = hits
                ranks[mode] = first_relevant_rank(hits, relevant)
            results.append(
                QueryResult(
                    pseudonym=pseudonym, question=question.key, passages_in_dossier=len(passages),
                    relevant=len(relevant), random_hit_at_3=round(random_hit_at_k(len(passages), len(relevant)), 4),
                    ranks=ranks, candidates_recall=first_relevant_rank(fused, relevant) is not None,
                )
            )

    by_question: dict[str, list[QueryResult]] = defaultdict(list)
    for result in results:
        by_question[result.question].append(result)
    strict = [r for r in results if r.question in STRICT]
    last = modes[-1]
    return Evaluation(
        dossiers=len(pseudonyms),
        queries=len(results),
        per_question_count={q.key: len(by_question[q.key]) for q in questions},
        modes={mode: _score(results, mode) for mode in modes},
        strict_modes={mode: _score(strict, mode) for mode in modes},
        per_question_hit_at_3={
            q.key: {mode: _score(by_question[q.key], mode).hit_at_3 for mode in modes} for q in questions
        },
        random_hit_at_3=round(sum(r.random_hit_at_3 for r in results) / (len(results) or 1), 4),
        random_hit_at_3_strict=round(sum(r.random_hit_at_3 for r in strict) / (len(strict) or 1), 4),
        random_per_question={
            q.key: round(sum(r.random_hit_at_3 for r in by_question[q.key]) / (len(by_question[q.key]) or 1), 4)
            for q in questions
        },
        candidates_recall=round(sum(r.candidates_recall for r in results) / (len(results) or 1), 4),
        failures=[
            f"{r.pseudonym} : {r.question} (rang {r.ranks[last]})"
            for r in results if r.ranks[last] is None or r.ranks[last] > 3
        ],
        results=results,
    )


def _pseudonyms(store: PassageStore) -> list[str]:
    return sorted({p.pseudonym for p in store.passages()})


def _connect(args, config: SearchConfig) -> PassageStore:
    client = open_client(config.qdrant, url=args.qdrant_url, path=args.qdrant_path)
    return PassageStore(client, config.qdrant.collection)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mesure la recherche sur un jeu de questions à réponse connue.")
    parser.add_argument("--qdrant-url", help="Serveur Qdrant (ex. http://127.0.0.1:6333)")
    parser.add_argument("--qdrant-path", help="Base Qdrant locale, sans serveur")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : search.toml)")
    parser.add_argument("--questions", type=Path, help="Jeu de questions (défaut : questions.toml)")
    parser.add_argument("--sans-reranking", action="store_true", help="N'évalue pas la chaîne avec re-ranking")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON des résultats")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    store = _connect(args, config)
    pseudonyms = _pseudonyms(store)
    if not pseudonyms:
        print("Aucun passage indexé.", file=sys.stderr)
        return 1
    questions = load_questions(args.questions)
    without = args.sans_reranking or not config.reranking.enabled
    modes = MODES[:-1] if without else MODES
    reranker = None if without else Reranker(config.reranking)
    retriever = Retriever(store, BgeM3(config.embedding), config, reranker)
    started = time.perf_counter()
    result = evaluate(store, retriever, questions, pseudonyms, modes)
    seconds = time.perf_counter() - started

    print(f"{result.dossiers} dossiers, {result.queries} questions posées en {seconds:.0f} s.")
    print("Dossiers évalués par question : " + ", ".join(f"{k} {v}" for k, v in result.per_question_count.items()))
    print(f"\n{'Chaîne':<15} {'rang 1':>7} {'top 3':>7} {'MRR':>6}   {'top 3, 5 questions strictes':>28}")
    for mode in modes:
        s, t = result.modes[mode], result.strict_modes[mode]
        print(f"{mode:<15} {s.hit_at_1:>7.1%} {s.hit_at_3:>7.1%} {s.mrr:>6.3f}   {t.hit_at_3:>28.1%}")
    print(f"{'hasard':<15} {'':>7} {result.random_hit_at_3:>7.1%} {'':>6}   {result.random_hit_at_3_strict:>28.1%}")
    print(f"\nPassages pertinents parmi les {config.retrieval.candidates} candidats de la fusion : "
          f"{result.candidates_recall:.1%}.")
    print(f"\n{'Question':<15} " + " ".join(f"{m:>14}" for m in modes) + f" {'hasard':>8}")
    for key, scores in result.per_question_hit_at_3.items():
        print(f"{key:<15} " + " ".join(f"{scores[m]:>14.1%}" for m in modes) + f" {result.random_per_question[key]:>8.1%}")
    print(f"\nÉchecs de la chaîne « {modes[-1]} » (aucun passage pertinent dans les 3 premiers) : {len(result.failures)}")
    for line in result.failures:
        print(f"  {line}")

    if args.out:
        export = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "code_version": __version__,
            "git_commit": git_commit(),
            "embedding_model": retriever.embedder.name,
            "reranking_model": reranker.name if reranker else None,
            "seconds": round(seconds, 1),
            "config": config.model_dump(mode="json"),
            "questions": [q.model_dump() for q in questions],
            "evaluation": result.model_dump(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Résultats écrits dans {args.out}.")
    return 0


def main_criteria(argv: list[str] | None = None) -> int:
    """Affiche, pour un dossier, les passages trouvés pour chaque critère de la grille."""
    parser = argparse.ArgumentParser(description="Passages trouvés pour chaque critère de la grille, dans un dossier.")
    parser.add_argument("pseudonyme", help="Pseudonyme du candidat (ex. C-1A2B3C4D)")
    parser.add_argument("--qdrant-url", help="Serveur Qdrant (ex. http://127.0.0.1:6333)")
    parser.add_argument("--qdrant-path", help="Base Qdrant locale, sans serveur")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : search.toml)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    grid = load_grid()
    store = _connect(args, config)
    needs = config.retrieval.mode == "hybrid_rerank" and config.reranking.enabled
    reranker = Reranker(config.reranking) if needs else None
    retriever = Retriever(store, BgeM3(config.embedding), config, reranker)
    encoded = retriever.encode([c.query for c in grid.criteria], release_embedder=reranker is not None)
    found = retriever.for_criteria(args.pseudonyme, grid, encoded=encoded)
    for criterion in grid.criteria:
        print(f"\n== {criterion.name}")
        for hit in found[criterion.key]:
            p = hit.passage
            where = p.label[:50] if p.label else (f"page {p.page}" if p.page else p.section)
            if p.start is not None:
                where += f", {p.start:g}-{p.end:g} s"
            print(f"  [{hit.score:+.2f}] {p.section} ({where}) : {p.text[:160].replace(chr(10), ' / ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
