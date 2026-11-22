"""Recherche hybride dans le dossier d'un candidat, puis re-ranking.

Pour une requête :

1. recherche dense (bge-m3) et recherche lexicale (poids creux de bge-m3) dans
   Qdrant, limitées au pseudonyme du candidat ;
2. fusion des deux listes par Reciprocal Rank Fusion (RRF), faite par Qdrant ;
3. re-ranking des meilleurs candidats par bge-reranker-v2-m3.

Les modes ``dense``, ``sparse`` et ``hybrid`` (sans re-ranking) existent pour
mesurer l'apport de chaque étage.

Mémoire : bge-m3 et le re-ranking pèsent chacun environ 2 Go et ne tiennent
pas ensemble sur la machine de développement. Encoder d'abord toutes les
requêtes (``encode(..., release_embedder=True)``), puis chercher et réordonner.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..grid import Grid
from .chunking import Passage
from .config import SearchConfig
from .embed import Embedder, Embedding
from .embed import release as release_bge_m3
from .rerank import Reranker
from .store import DENSE, SPARSE, PassageStore

Mode = Literal["dense", "sparse", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("dense", "sparse", "hybrid", "hybrid_rerank")


class Hit(BaseModel):
    passage: Passage
    score: float  # score du dernier étage (similarité, score RRF ou score du re-ranking)
    fused_rank: int | None = None  # rang avant re-ranking


class Retriever:
    def __init__(self, store: PassageStore, embedder: Embedder, config: SearchConfig, reranker: Reranker | None = None):
        self.store = store
        self.embedder = embedder
        self.config = config
        self.reranker = reranker

    def candidates(self, pseudonym: str, query: Embedding, mode: Mode, limit: int) -> list[Hit]:
        """Candidats d'une requête déjà encodée (dense, lexicale, ou fusion RRF des deux)."""
        from qdrant_client import models

        only = self.store._only(pseudonym)
        sparse = models.SparseVector(indices=list(query.sparse), values=list(query.sparse.values()))
        prefetch = self.config.retrieval.prefetch_limit
        # Les ex aequo (fréquents après fusion RRF) reviennent dans un ordre arbitraire :
        # on demande tout ce que la fusion peut rendre, puis on trie par score et identifiant.
        wanted = max(limit, 2 * prefetch)
        if mode == "dense":
            response = self.store.client.query_points(
                self.store.collection, query=query.dense, using=DENSE, query_filter=only, limit=wanted, with_payload=True
            )
        elif mode == "sparse":
            response = self.store.client.query_points(
                self.store.collection, query=sparse, using=SPARSE, query_filter=only, limit=wanted, with_payload=True
            )
        else:
            response = self.store.client.query_points(
                self.store.collection,
                prefetch=[
                    models.Prefetch(query=query.dense, using=DENSE, filter=only, limit=prefetch),
                    models.Prefetch(query=sparse, using=SPARSE, filter=only, limit=prefetch),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=wanted,
                with_payload=True,
            )
        fields = Passage.model_fields
        points = sorted(response.points, key=lambda point: (-point.score, str(point.id)))[:limit]
        return [
            Hit(passage=Passage(**{k: v for k, v in point.payload.items() if k in fields}), score=point.score,
                fused_rank=rank)
            for rank, point in enumerate(points, start=1)
        ]

    def encode(self, queries: list[str], release_embedder: bool = False) -> list[Embedding]:
        """Encode les requêtes ; ``release_embedder`` libère ensuite bge-m3 (avant le re-ranking)."""
        encoded = self.embedder.encode(queries)
        if release_embedder:
            release_bge_m3()
        return encoded

    @property
    def default_mode(self) -> Mode:
        """Chaîne de la configuration ; sans re-ranking activé, l'hybride remplace l'hybride re-classé."""
        mode = self.config.retrieval.mode
        if mode == "hybrid_rerank" and not (self.config.reranking.enabled and self.reranker is not None):
            return "hybrid"
        return mode

    @property
    def needs_reranker(self) -> bool:
        return self.config.retrieval.mode == "hybrid_rerank" and self.config.reranking.enabled

    def search_many(
        self, pseudonym: str, queries: list[str], mode: Mode | None = None, top_k: int | None = None,
        encoded: list[Embedding] | None = None,
    ) -> list[list[Hit]]:
        """Passages les plus pertinents pour chaque requête, dans le dossier du candidat.

        Les requêtes sont souvent les mêmes pour tous les dossiers (critères de la
        grille) : les encoder une fois avec ``encode`` et passer ``encoded``.
        """
        mode = mode or self.default_mode
        top_k = top_k or self.config.retrieval.top_k
        encoded = encoded if encoded is not None else self.encode(queries)
        limit = self.config.retrieval.candidates if mode == "hybrid_rerank" else top_k
        candidates = [self.candidates(pseudonym, q, mode, limit) for q in encoded]
        if mode != "hybrid_rerank":
            return [hits[:top_k] for hits in candidates]
        return [self.rerank(query, hits, top_k) for query, hits in zip(queries, candidates)]

    def rerank(self, query: str, hits: list[Hit], top_k: int) -> list[Hit]:
        """Réordonne les candidats par le score du re-ranking."""
        if self.reranker is None:
            raise ValueError("Re-ranking demandé sans modèle de re-ranking.")
        reranked = [hit.model_copy() for hit in hits]
        scores = self.reranker.score(query, [h.passage.text for h in reranked]) if reranked else []
        for hit, score in zip(reranked, scores):
            hit.score = score
        return sorted(reranked, key=lambda h: h.score, reverse=True)[:top_k]

    def for_criteria(
        self, pseudonym: str, grid: Grid, top_k: int | None = None, encoded: list[Embedding] | None = None
    ) -> dict[str, list[Hit]]:
        """Une requête par critère de la grille, limitée au dossier du candidat."""
        hits = self.search_many(pseudonym, [c.query for c in grid.criteria], top_k=top_k, encoded=encoded)
        return {criterion.key: found for criterion, found in zip(grid.criteria, hits)}
