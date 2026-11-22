"""Embeddings denses et creux avec bge-m3, calculés en local sur le processeur.

Le calcul reprend celui de la bibliothèque de référence (FlagEmbedding,
``BGEM3FlagModel``), sans en dépendre :

- **dense** : état caché du premier jeton (CLS), normalisé ;
- **creux** : ``relu(sparse_linear(état caché))`` pour chaque jeton, jetons
  spéciaux exclus ; un jeton présent plusieurs fois garde son poids maximal.

Le test ``test_bge_m3_matches_model_card`` vérifie que ce calcul redonne les
valeurs publiées dans la fiche du modèle.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Protocol

from .config import EmbeddingRule


@dataclass
class Embedding:
    dense: list[float]
    sparse: dict[int, float]
    tokens: int  # nombre de jetons du texte, avant toute troncature
    truncated: bool


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> list[Embedding]: ...


@cache
def _load(model: str, revision: str):
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModel, AutoTokenizer

    path = snapshot_download(
        model,
        revision=revision,
        allow_patterns=[
            "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
            "sentencepiece.bpe.model", "pytorch_model.bin", "sparse_linear.pt",
        ],
    )
    tokenizer = AutoTokenizer.from_pretrained(path)
    encoder = AutoModel.from_pretrained(path, low_cpu_mem_usage=True).eval()
    sparse = torch.nn.Linear(encoder.config.hidden_size, 1)
    sparse.load_state_dict(torch.load(f"{path}/sparse_linear.pt", map_location="cpu", weights_only=True))
    sparse.eval()
    return tokenizer, encoder, sparse


def release() -> None:
    """Libère la mémoire du modèle (2 Go environ), par exemple avant de charger le re-ranking."""
    import gc

    _load.cache_clear()
    gc.collect()


class BgeM3:
    """Encodeur bge-m3 : chargé au premier appel, gardé ensuite en mémoire."""

    def __init__(self, rule: EmbeddingRule) -> None:
        self.rule = rule
        self.name = f"{rule.model}@{rule.revision[:12]}"

    def lexical_tokens(self, weights: dict[int, float]) -> dict[str, float]:
        """Poids lexicaux lisibles (jeton -> poids), pour contrôle."""
        tokenizer, _, _ = _load(self.rule.model, self.rule.revision)
        return {tokenizer.convert_ids_to_tokens(i).lstrip("▁"): w for i, w in weights.items()}

    def encode(self, texts: list[str]) -> list[Embedding]:
        import torch

        tokenizer, encoder, sparse = _load(self.rule.model, self.rule.revision)
        special = set(tokenizer.all_special_ids)
        results: list[Embedding] = []
        for start in range(0, len(texts), self.rule.batch_size):
            batch_texts = texts[start:start + self.rule.batch_size]
            lengths = [len(tokenizer(text)["input_ids"]) for text in batch_texts]
            batch = tokenizer(
                batch_texts, padding=True, truncation=True, max_length=self.rule.max_tokens, return_tensors="pt"
            )
            with torch.inference_mode():
                hidden = encoder(**batch).last_hidden_state
                dense = torch.nn.functional.normalize(hidden[:, 0], dim=-1)
                weights = torch.relu(sparse(hidden)).squeeze(-1)
            for row, length in enumerate(lengths):
                lexical: dict[int, float] = {}
                for token, weight in zip(batch["input_ids"][row].tolist(), weights[row].tolist()):
                    if token in special or weight <= 0:
                        continue
                    if weight > lexical.get(token, 0.0):
                        lexical[token] = weight
                results.append(
                    Embedding(
                        dense=dense[row].tolist(),
                        sparse=lexical,
                        tokens=length,
                        truncated=length > self.rule.max_tokens,
                    )
                )
        return results


def lexical_score(left: dict[int, float], right: dict[int, float]) -> float:
    """Score lexical de bge-m3 : somme des produits des poids des jetons communs."""
    return sum(weight * right[token] for token, weight in left.items() if token in right)
