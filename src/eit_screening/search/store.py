"""Stockage des passages dans Qdrant : un vecteur dense et un vecteur creux par passage.

Une seule collection ; le pseudonyme est indexé pour limiter une recherche au
dossier d'un candidat. Réindexer un dossier efface d'abord ses passages.
Aucun numéro de candidature n'est stocké : seulement le pseudonyme.
"""

from __future__ import annotations

from pathlib import Path

from .chunking import Passage
from .config import QdrantRule
from .embed import Embedding

DENSE, SPARSE = "dense", "sparse"


def open_client(rule: QdrantRule, url: str | None = None, path: str | Path | None = None):
    """Client Qdrant : serveur si une adresse est donnée, sinon base locale sur disque (ou en mémoire)."""
    from qdrant_client import QdrantClient

    url = url if url is not None else rule.url
    if url:
        return QdrantClient(url=url)
    location = str(path if path is not None else rule.path)
    if location == ":memory:":
        return QdrantClient(":memory:")
    Path(location).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=location)


class PassageStore:
    def __init__(self, client, collection: str) -> None:
        self.client = client
        self.collection = collection

    def ensure(self, dense_size: int) -> None:
        from qdrant_client import models

        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dense_size, distance=models.Distance.COSINE)},
            # Poids lexicaux de bge-m3 stockés tels quels, sans pondération IDF.
            sparse_vectors_config={SPARSE: models.SparseVectorParams()},
        )
        self.client.create_payload_index(self.collection, "pseudonym", models.PayloadSchemaType.KEYWORD)

    def _only(self, pseudonym: str):
        from qdrant_client import models

        return models.Filter(must=[models.FieldCondition(key="pseudonym", match=models.MatchValue(value=pseudonym))])

    def replace_dossier(self, pseudonym: str, passages: list[Passage], embeddings: list[Embedding], model: str) -> None:
        """Remplace tous les passages d'un dossier."""
        from qdrant_client import models

        if self.client.collection_exists(self.collection):
            self.client.delete(self.collection, points_selector=models.FilterSelector(filter=self._only(pseudonym)))
        points = [
            models.PointStruct(
                id=passage.id,
                vector={
                    DENSE: embedding.dense,
                    SPARSE: models.SparseVector(
                        indices=list(embedding.sparse.keys()), values=list(embedding.sparse.values())
                    ),
                },
                payload={**passage.model_dump(), "embedding_model": model, "tokens": embedding.tokens},
            )
            for passage, embedding in zip(passages, embeddings, strict=True)
        ]
        if points:
            self.client.upsert(self.collection, points=points)

    def passages(self, pseudonym: str | None = None) -> list[Passage]:
        """Tous les passages stockés (ou ceux d'un dossier), relus depuis Qdrant."""
        found, offset = [], None
        while True:
            points, offset = self.client.scroll(
                self.collection, scroll_filter=self._only(pseudonym) if pseudonym else None,
                limit=256, offset=offset, with_payload=True, with_vectors=False,
            )
            fields = Passage.model_fields
            found += [Passage(**{k: v for k, v in p.payload.items() if k in fields}) for p in points]
            if offset is None:
                return found

    def count(self) -> int:
        return self.client.count(self.collection).count
