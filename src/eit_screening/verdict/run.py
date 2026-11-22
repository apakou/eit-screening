"""Ligne de commande : un verdict proposé par dossier anonymisé, avec journal de chaque appel."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..grid import load_grid
from ..screening.common import Finding, git_commit
from ..search.config import load_config as load_search_config
from ..search.embed import BgeM3
from ..search.index import read_dossiers
from ..search.rerank import Reranker
from ..search.retrieve import Retriever
from ..search.store import PassageStore, open_client
from .client import ChatClient
from .models import load_config
from .propose import PROMPT_VERSION, propose


def load_findings(table: Path | None, eligibility: Path | None, assessment: Path | None) -> dict[str, list[Finding]]:
    """Constats des étapes 1 et 2, rangés par pseudonyme (la table reste locale)."""
    if table is None:
        return {}
    entries = json.loads(table.expanduser().read_text(encoding="utf-8"))["entries"]
    by_id: dict[str, list[Finding]] = {}
    if eligibility and eligibility.exists():
        for report in json.loads(eligibility.read_text(encoding="utf-8"))["reports"]:
            by_id.setdefault(report["application_id"], []).extend(Finding(**f) for f in report["findings"])
    if assessment and assessment.exists():
        for match in json.loads(assessment.read_text(encoding="utf-8"))["result"]["matches"]:
            by_id.setdefault(match["application_id"], []).extend(Finding(**f) for f in match["findings"])
    return {entries[app_id]: found for app_id, found in by_id.items() if app_id in entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose un verdict et ses raisons pour chaque dossier anonymisé.")
    parser.add_argument("anonymises", type=Path, help="Dossier de sortie de eit-anonymize")
    parser.add_argument("-o", "--out", type=Path, default=Path("data/verdicts"), help="Dossier des verdicts")
    parser.add_argument("--qdrant-url", help="Serveur Qdrant (ex. http://127.0.0.1:6333)")
    parser.add_argument("--qdrant-path", help="Base Qdrant locale, sans serveur")
    parser.add_argument("--table", type=Path, help="Table de correspondance, pour joindre les constats des étapes 1 et 2")
    parser.add_argument("--eligibilite", type=Path, default=Path("data/resultats/eligibilite.json"))
    parser.add_argument("--appariement", type=Path, default=Path("data/resultats/appariement.json"))
    parser.add_argument("--config", type=Path, help="Paramètres du verdict (défaut : verdict.toml)")
    parser.add_argument("--limite", type=int, help="Nombre maximal de dossiers (essai)")
    parser.add_argument(
        "--dossier-entier", action="store_true",
        help="Variante de comparaison sans recherche : tout le dossier anonymisé dans le prompt",
    )
    parser.add_argument("--resume", type=Path, help="Fichier JSON du résumé (défaut : <out>/_resume.json)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    search_config = load_search_config()
    grid = load_grid()
    dossiers = read_dossiers(args.anonymises)[: args.limite]
    if not dossiers:
        print(f"Aucun dossier anonymisé dans {args.anonymises}.", file=sys.stderr)
        return 1
    findings = load_findings(args.table, args.eligibilite, args.appariement)

    store = PassageStore(open_client(search_config.qdrant, url=args.qdrant_url, path=args.qdrant_path),
                         search_config.qdrant.collection)
    needs_reranker = search_config.retrieval.mode == "hybrid_rerank" and search_config.reranking.enabled
    reranker = Reranker(search_config.reranking) if needs_reranker else None
    retriever = Retriever(store, BgeM3(search_config.embedding), search_config, reranker)
    # Les requêtes des critères sont les mêmes pour tous les dossiers : encodées une fois,
    # puis bge-m3 est libéré (2 Go), le modèle de langage ayant besoin de la mémoire.
    encoded = [] if args.dossier_entier else retriever.encode(
        [c.query for c in grid.criteria], release_embedder=True
    )
    client = ChatClient(config.llm)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"{'Pseudonyme':<12} {'Total':>5}  {'Citations':>9}  {'Essais':>6} {'Durée':>6}  Verdict proposé")
    verdicts = []
    for dossier in dossiers:
        evidence = {} if args.dossier_entier else retriever.for_criteria(
            dossier.pseudonym, grid, top_k=config.retrieval.passages_per_criterion, encoded=encoded
        )
        verdict, messages, result = propose(
            dossier, evidence, grid, client, config, findings.get(dossier.pseudonym, []), full_dossier=args.dossier_entier
        )
        verdicts.append(verdict)
        (args.out / f"{dossier.pseudonym}.json").write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
        call = {
            "pseudonym": dossier.pseudonym,
            "prompt_version": PROMPT_VERSION,
            "model": config.llm.model,
            "base_url": config.llm.base_url,
            "retrieval_mode": "dossier entier" if args.dossier_entier else retriever.default_mode,
            "passages": {k: [h.passage.model_dump() for h in hits] for k, hits in evidence.items()},
            "messages": messages,
            "responses": result.raw,
            "errors": result.errors,
        }
        (args.out / f"{dossier.pseudonym}.appel.json").write_text(
            json.dumps(call, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total = "-" if verdict.total is None else str(verdict.total)
        print(f"{verdict.pseudonym:<12} {total:>5}  {verdict.quotes_verified:>4}/{verdict.quotes_total:<4}  "
              f"{verdict.llm.attempts:>6} {verdict.llm.seconds:>5.0f}s  {verdict.proposed}")

    valid = sum(v.llm.schema_valid for v in verdicts)
    quotes = sum(v.quotes_total for v in verdicts)
    verified = sum(v.quotes_verified for v in verdicts)
    seconds = sum(v.llm.seconds for v in verdicts)
    distribution = Counter(v.proposed for v in verdicts)
    # Note supérieure à 0 sans aucune citation : raison non appuyée par le dossier.
    unsupported = sum(1 for v in verdicts for c in v.criteria if c.score > 0 and not c.quote)
    scored = sum(1 for v in verdicts for c in v.criteria if c.score > 0)
    print(f"\n{len(verdicts)} verdicts ; conformes au schéma : {valid}/{len(verdicts)} ; "
          f"citations vérifiées mot pour mot : {verified}/{quotes}"
          + (f" ({verified / quotes:.1%})" if quotes else "") + f" ; {seconds / len(verdicts):.0f} s par dossier.")
    print("Verdicts proposés : " + ", ".join(f"{k} {v}" for k, v in sorted(distribution.items())))
    print(f"Notes supérieures à 0 sans citation : {unsupported}/{scored}.")
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_commit": git_commit(),
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "prompt_version": PROMPT_VERSION,
        "retrieval_mode": "dossier entier" if args.dossier_entier else retriever.default_mode,
        "decision_rule": config.decision.model_dump(),
        "dossiers": len(verdicts),
        "schema_valid": valid,
        "quotes_total": quotes,
        "quotes_verified": verified,
        "quote_verification_rate": round(verified / quotes, 4) if quotes else None,
        "seconds_per_dossier": round(seconds / len(verdicts), 1),
        "scores_without_quote": unsupported,
        "scores_above_zero": scored,
        "verdicts": dict(sorted(distribution.items())),
    }
    summary_path = args.resume or args.out / "_resume.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résumé écrit dans {summary_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
