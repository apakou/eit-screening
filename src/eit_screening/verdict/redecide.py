"""Recalcul des décisions proposées sans rappeler le modèle de langage.

Un verdict contient deux parties :

- ce que le modèle a produit (notes, raisons, citations, avis sur les réponses
  génériques) : coûteux à refaire (environ une heure pour 40 dossiers) ;
- ce que le code en déduit (constats des étapes 1 et 2, Concerns relevés par
  les contrôles, règle de décision, revue complémentaire).

Cette commande garde la première partie telle quelle et recalcule la seconde :
après un changement des contrôles, de la règle de décision ou des textes
affichés aux évaluateurs. Les vérifications de citations ne changent pas.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from ..grid import load_grid
from ..screening.common import git_commit
from .models import Verdict, load_config
from .propose import concerns_from_findings, decide
from .run import load_findings


def redecide(verdict: Verdict, findings, grid, config) -> Verdict:
    """Même verdict, constats et décision recalculés ; notes et citations du modèle inchangées."""
    # Concerns du modèle gardés, sous le libellé actuel de la grille.
    names = {c.key: c.name for c in grid.concerns}
    model_concerns = [
        c.model_copy(update={"name": names.get(c.key, c.name)}) for c in verdict.concerns if c.source == "modèle"
    ]
    concerns = concerns_from_findings(findings, grid) + model_concerns
    quoted = [c for c in verdict.criteria if c.quote]
    unverified = sum(not c.quote_verified for c in quoted)
    decision = decide(verdict.total, findings, concerns, unverified, verdict.llm.schema_valid, config.decision)
    return verdict.model_copy(
        update={
            "findings": findings,
            "concerns": concerns,
            "proposed": decision.proposed,
            "request_further_review": decision.request_further_review,
            "rule": decision.rule,
            "review_reasons": decision.review_reasons,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recalcule constats et décisions proposées à partir des verdicts existants, sans le modèle."
    )
    parser.add_argument("--verdicts", type=Path, default=Path("data/verdicts"))
    parser.add_argument("--table", type=Path, required=True, help="Table de correspondance")
    parser.add_argument("--eligibilite", type=Path, default=Path("data/resultats/eligibilite.json"))
    parser.add_argument("--appariement", type=Path, default=Path("data/resultats/appariement.json"))
    parser.add_argument("--config", type=Path, help="Paramètres du verdict (défaut : verdict.toml)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    grid = load_grid()
    findings = load_findings(args.table, args.eligibilite, args.appariement)
    paths = [p for p in sorted(args.verdicts.glob("C-*.json")) if not p.name.endswith(".appel.json")]
    if not paths:
        print(f"Aucun verdict dans {args.verdicts}.", file=sys.stderr)
        return 1

    changed = 0
    verdicts = []
    for path in paths:
        before = Verdict.model_validate_json(path.read_text(encoding="utf-8"))
        after = redecide(before, findings.get(before.pseudonym, []), grid, config)
        changed += (before.proposed, before.request_further_review) != (after.proposed, after.request_further_review)
        path.write_text(after.model_dump_json(indent=2), encoding="utf-8")
        verdicts.append(after)

    distribution = Counter(v.proposed or "aucune" for v in verdicts)
    review = sum(v.request_further_review for v in verdicts)
    summary_path = args.verdicts / "_resume.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    summary.update({
        "recomputed_at": datetime.now().isoformat(timespec="seconds"),
        "recomputed_git_commit": git_commit(),
        "decision_rule": config.decision.model_dump(),
        "verdicts": dict(sorted(distribution.items())),
        "request_further_review": review,
    })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(verdicts)} verdicts recalculés sans le modèle ; décision ou revue changée pour {changed}.")
    print("Décisions proposées : " + ", ".join(f"{k} {v}" for k, v in sorted(distribution.items()))
          + f" ; revue complémentaire demandée : {review}/{len(verdicts)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
