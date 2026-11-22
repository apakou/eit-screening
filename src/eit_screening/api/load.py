"""Charge les verdicts proposés et les dossiers anonymisés dans la base.

Recharger met à jour les candidatures ; le journal des décisions n'est jamais
touché.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import Candidate, database_url, make_engine, make_sessionmaker, now


def load(verdicts: Path, anonymized: Path, url: str | None = None, sessions=None) -> int:
    """Charge les verdicts ; ``sessions`` permet de réutiliser la base d'une application déjà créée."""
    sessions = sessions or make_sessionmaker(make_engine(url))
    count = 0
    with sessions() as db:
        for path in sorted(verdicts.glob("C-*.json")):
            if path.name.endswith(".appel.json"):
                continue
            verdict = json.loads(path.read_text(encoding="utf-8"))
            dossier_path = anonymized / f"{verdict['pseudonym']}.json"
            if not dossier_path.exists():
                print(f"{verdict['pseudonym']} : dossier anonymisé introuvable, ignoré.", file=sys.stderr)
                continue
            dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
            row = db.get(Candidate, verdict["pseudonym"]) or Candidate(pseudonym=verdict["pseudonym"])
            row.proposed = verdict["proposed"]
            row.total = verdict["total"]
            row.max_total = verdict["max_total"]
            row.alerts = sum(f["severity"] == "alert" for f in verdict["findings"])
            row.concerns = len(verdict["concerns"])
            row.quotes_verified = verdict["quotes_verified"]
            row.quotes_total = verdict["quotes_total"]
            row.metadata_json = dossier["metadata"]
            row.verdict = verdict
            row.dossier = {"pseudonym": dossier["pseudonym"], "texts": dossier["texts"]}
            row.loaded_at = now()
            db.add(row)
            count += 1
        db.commit()
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Charge verdicts et dossiers anonymisés dans la base de l'API.")
    parser.add_argument("--verdicts", type=Path, default=Path("data/verdicts"))
    parser.add_argument("--anonymises", type=Path, default=Path("data/anonymises"))
    parser.add_argument("--database-url", help=f"Défaut : variable EIT_DATABASE_URL ou {database_url()}")
    args = parser.parse_args(argv)
    count = load(args.verdicts, args.anonymises, args.database_url)
    print(f"{count} candidatures chargées.")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
