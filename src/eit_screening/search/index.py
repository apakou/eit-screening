"""Indexation des dossiers anonymisés : découpage, embeddings bge-m3, stockage dans Qdrant.

Seuls les dossiers anonymisés sont lus (sortie de ``eit-anonymize``) : ni PDF,
ni table de correspondance, ni numéro de candidature.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .. import __version__
from ..privacy.anonymize import AnonymizedDossier
from ..screening.common import git_commit
from .chunking import chunk_dossier, passage_text
from .config import SearchConfig, load_config
from .embed import BgeM3, Embedder
from .store import PassageStore, open_client


def read_dossiers(folder: Path) -> list[AnonymizedDossier]:
    """Dossiers anonymisés d'un dossier de sortie (le résumé ``_resume.json`` est ignoré)."""
    return [
        AnonymizedDossier.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.json"))
        if not path.name.startswith("_")
    ]


class IndexReport(BaseModel):
    dossiers: int = 0
    passages: int = 0
    by_section: dict[str, int] = Field(default_factory=dict)
    truncated: int = 0
    max_tokens_seen: int = 0
    seconds: float = 0.0


def index_dossiers(
    dossiers: list[AnonymizedDossier], store: PassageStore, embedder: Embedder, config: SearchConfig
) -> IndexReport:
    report = IndexReport()
    sections: Counter[str] = Counter()
    started = time.perf_counter()
    for dossier in dossiers:
        passages = chunk_dossier(dossier, config.chunking)
        embeddings = embedder.encode([p.text for p in passages]) if passages else []
        if embeddings:
            store.ensure(len(embeddings[0].dense))
        store.replace_dossier(dossier.pseudonym, passages, embeddings, embedder.name)
        report.dossiers += 1
        report.passages += len(passages)
        sections.update(p.section for p in passages)
        report.truncated += sum(e.truncated for e in embeddings)
        report.max_tokens_seen = max([report.max_tokens_seen, *(e.tokens for e in embeddings)])
    report.by_section = dict(sorted(sections.items()))
    report.seconds = round(time.perf_counter() - started, 1)
    return report


class LocationCheck(BaseModel):
    passages: int
    located: int
    mismatches: list[str] = Field(default_factory=list)
    uncovered_units: list[str] = Field(default_factory=list)


def check_locations(store: PassageStore, dossiers: list[AnonymizedDossier], sections: list[str]) -> LocationCheck:
    """Relit chaque passage dans Qdrant et vérifie qu'il pointe exactement vers son texte.

    Vérifie aussi que tout le texte indexable est couvert par au moins un passage.
    """
    by_pseudonym = {d.pseudonym: d for d in dossiers}
    stored = store.passages()
    mismatches: list[str] = []
    covered: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for passage in stored:
        dossier = by_pseudonym.get(passage.pseudonym)
        if dossier is None:
            mismatches.append(f"{passage.pseudonym} : dossier absent")
            continue
        first, last = dossier.texts[passage.unit_start], dossier.texts[passage.unit_end]
        ok = (
            passage_text(passage, dossier) == passage.text
            and first.section == passage.section
            and first.label == passage.label
            and first.page == passage.page
            and first.start == passage.start
            and last.end == passage.end
        )
        if not ok:
            mismatches.append(f"{passage.pseudonym} : passage {passage.id}")
        for unit in range(passage.unit_start, passage.unit_end + 1):
            lo = passage.char_start if unit == passage.unit_start else 0
            hi = passage.char_end if unit == passage.unit_end else len(dossier.texts[unit].text)
            covered.setdefault((passage.pseudonym, unit), []).append((lo, hi))
    uncovered: list[str] = []
    for dossier in dossiers:
        for index, unit in enumerate(dossier.texts):
            if unit.section not in sections or not unit.text.strip():
                continue
            spans = covered.get((dossier.pseudonym, index), [])
            missing = [i for i, c in enumerate(unit.text) if not c.isspace() and not any(lo <= i < hi for lo, hi in spans)]
            if missing:
                uncovered.append(f"{dossier.pseudonym} : texte {index} ({unit.section})")
    return LocationCheck(
        passages=len(stored), located=len(stored) - len(mismatches), mismatches=mismatches, uncovered_units=uncovered
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Découpe les dossiers anonymisés et les indexe dans Qdrant (bge-m3).")
    parser.add_argument("anonymises", type=Path, help="Dossier de sortie de eit-anonymize")
    parser.add_argument("--qdrant-url", help="Serveur Qdrant (ex. http://127.0.0.1:6333) ; défaut : search.toml")
    parser.add_argument("--qdrant-path", help="Base Qdrant locale, sans serveur ; défaut : search.toml")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : search.toml)")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON du rapport")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    dossiers = read_dossiers(args.anonymises)
    if not dossiers:
        print(f"Aucun dossier anonymisé dans {args.anonymises}.", file=sys.stderr)
        return 1
    client = open_client(config.qdrant, url=args.qdrant_url, path=args.qdrant_path)
    store = PassageStore(client, config.qdrant.collection)
    embedder = BgeM3(config.embedding)
    report = index_dossiers(dossiers, store, embedder, config)
    check = check_locations(store, dossiers, config.chunking.sections)

    print(f"{report.dossiers} dossiers indexés, {report.passages} passages en {report.seconds:g} s "
          f"({report.seconds / max(report.passages, 1):.2f} s par passage).")
    print("Passages par section : " + ", ".join(f"{k} {v}" for k, v in report.by_section.items()))
    print(f"Jetons par passage : au plus {report.max_tokens_seen} ; passages tronqués : {report.truncated}.")
    print(f"Points dans Qdrant : {store.count()}. Emplacement retrouvé exactement : {check.located}/{check.passages} ; "
          f"textes non couverts : {len(check.uncovered_units)}.")
    for line in check.mismatches + check.uncovered_units:
        print(f"  {line}")

    if args.out:
        export = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "code_version": __version__,
            "git_commit": git_commit(),
            "embedding_model": embedder.name,
            "qdrant": args.qdrant_url or config.qdrant.url or (args.qdrant_path or config.qdrant.path),
            "config": config.model_dump(mode="json"),
            "report": report.model_dump(),
            "location_check": check.model_dump(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rapport écrit dans {args.out}.")
    return 0 if not check.mismatches and not check.uncovered_units else 1


if __name__ == "__main__":
    raise SystemExit(main())
