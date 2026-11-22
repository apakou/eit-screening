"""Re-ranking des passages avec bge-reranker-v2-m3, en local sur le processeur.

Le modèle lit la question et le passage ensemble et donne un score de
pertinence (logit ; plus il est haut, plus le passage répond). Le test
``test_reranker_matches_model_card`` vérifie les valeurs de la fiche du modèle.
"""

from __future__ import annotations

import gc
from functools import cache

from .config import RerankingRule


@cache
def _load(model: str, revision: str):
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    path = snapshot_download(model, revision=revision)
    tokenizer = AutoTokenizer.from_pretrained(path)
    scorer = AutoModelForSequenceClassification.from_pretrained(path, low_cpu_mem_usage=True).eval()
    return tokenizer, scorer


def release() -> None:
    """Libère la mémoire du modèle (2 Go environ)."""
    _load.cache_clear()
    gc.collect()


class Reranker:
    def __init__(self, rule: RerankingRule) -> None:
        self.rule = rule
        self.name = f"{rule.model}@{rule.revision[:12]}"

    def score(self, query: str, passages: list[str]) -> list[float]:
        import torch

        tokenizer, scorer = _load(self.rule.model, self.rule.revision)
        scores: list[float] = []
        for start in range(0, len(passages), self.rule.batch_size):
            pairs = [[query, text] for text in passages[start:start + self.rule.batch_size]]
            batch = tokenizer(pairs, padding=True, truncation=True, max_length=self.rule.max_tokens, return_tensors="pt")
            with torch.inference_mode():
                scores += scorer(**batch).logits.view(-1).float().tolist()
        return scores
