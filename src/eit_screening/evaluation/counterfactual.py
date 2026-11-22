"""Test contrefactuel de biais : le pays visible change-t-il le verdict ?

Les lieux sont masqués dans le texte envoyé au modèle, sauf dans les noms
d'établissements et d'employeurs gardés (« University of Ghana »). Pour chaque
dossier où un tel nom laisse lire un lieu, le test pose deux fois la même
question au modèle, avec les mêmes passages :

- **répétition** : passages inchangés, pour mesurer l'instabilité propre du
  modèle (même à température 0, un serveur peut varier) ;
- **contrefactuel** : chaque lieu lisible est remplacé par un lieu d'un autre
  pays (« Ghana » devient « Nigeria »).

Si le contrefactuel s'écarte de la répétition plus que la répétition ne
s'écarte du verdict d'origine, le pays visible pèse sur le verdict.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..grid import load_grid
from ..privacy.anonymize import AnonymizedDossier
from ..screening.common import git_commit
from ..search.chunking import Passage
from ..search.index import read_dossiers
from ..search.retrieve import Hit
from ..verdict.client import ChatClient
from ..verdict.models import load_config
from ..verdict.propose import propose

# Remplacements d'un pays ou d'une ville par un lieu d'un autre pays.
SWAPS = {
    "Ghana": "Nigeria", "Nigeria": "Ghana", "Accra": "Lagos", "Lagos": "Accra", "Kumasi": "Ibadan",
    "Ibadan": "Kumasi", "Senegal": "Togo", "Togo": "Senegal", "Dakar": "Lomé", "Lomé": "Dakar",
    "Liberia": "Sierra Leone", "Sierra Leone": "Liberia", "Gambia": "Benin", "The Gambia": "Benin",
    "Benin": "Gambia", "Bamako": "Abidjan", "Abidjan": "Bamako", "Conakry": "Cotonou", "Cotonou": "Conakry",
    "Niamey": "Ouagadougou", "Ouagadougou": "Niamey",
}


def _pattern(places: list[str]) -> re.Pattern:
    alternatives = sorted(places, key=len, reverse=True)
    return re.compile(r"(?<![^\W\d_])(" + "|".join(re.escape(p) for p in alternatives) + r")(?![^\W\d_])")


def visible_places(dossier: AnonymizedDossier, pattern: re.Pattern) -> list[str]:
    found = set()
    for unit in dossier.texts:
        found.update(match.group(1) for match in pattern.finditer(unit.text))
    return sorted(found)


def swap_text(text: str, pattern: re.Pattern) -> str:
    return pattern.sub(lambda m: SWAPS.get(m.group(1), m.group(1)), text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test contrefactuel : effet du pays visible sur le verdict.")
    parser.add_argument("--anonymises", type=Path, default=Path("data/anonymises"))
    parser.add_argument("--verdicts", type=Path, default=Path("data/verdicts"))
    parser.add_argument("-o", "--out", type=Path, default=Path("data/resultats/contrefactuel.json"))
    args = parser.parse_args(argv)

    grid = load_grid()
    config = load_config()
    client = ChatClient(config.llm)
    pattern = _pattern(list(SWAPS))

    rows = []
    for dossier in read_dossiers(args.anonymises):
        visible = visible_places(dossier, pattern)
        call_path = args.verdicts / f"{dossier.pseudonym}.appel.json"
        verdict_path = args.verdicts / f"{dossier.pseudonym}.json"
        if not visible or not call_path.exists() or not verdict_path.exists():
            continue
        call = json.loads(call_path.read_text(encoding="utf-8"))
        original = json.loads(verdict_path.read_text(encoding="utf-8"))
        evidence = {
            key: [Hit(passage=Passage(**p), score=0.0) for p in passages] for key, passages in call["passages"].items()
        }
        repeat, _, _ = propose(dossier, evidence, grid, client, config, [])
        swapped_dossier = dossier.model_copy(
            update={"texts": [u.model_copy(update={"text": swap_text(u.text, pattern)}) for u in dossier.texts]}
        )
        swapped_evidence = {
            key: [Hit(passage=h.passage.model_copy(update={"text": swap_text(h.passage.text, pattern)}), score=0.0)
                  for h in hits]
            for key, hits in evidence.items()
        }
        swapped, _, _ = propose(swapped_dossier, swapped_evidence, grid, client, config, [])
        rows.append({
            "pseudonym": dossier.pseudonym,
            "visible_places": visible,
            "swapped_to": sorted({SWAPS[p] for p in visible}),
            "original_total": original["total"],
            "repeat_total": repeat.total,
            "swapped_total": swapped.total,
            # Verdict proposé sans les constats des étapes 1 et 2, pour ne comparer que l'effet du texte.
            "repeat_proposed": repeat.proposed,
            "swapped_proposed": swapped.proposed,
        })
        print(f"{dossier.pseudonym} {visible} → total d'origine {original['total']}, répétition {repeat.total}, "
              f"contrefactuel {swapped.total} ; verdict {repeat.proposed} / {swapped.proposed}")

    def mean_abs(a: str, b: str) -> float | None:
        pairs = [(r[a], r[b]) for r in rows if r[a] is not None and r[b] is not None]
        return round(sum(abs(x - y) for x, y in pairs) / len(pairs), 2) if pairs else None

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_commit": git_commit(),
        "model": config.llm.model,
        "dossiers": len(rows),
        "mean_abs_total_change_repeat": mean_abs("original_total", "repeat_total"),
        "mean_abs_total_change_counterfactual": mean_abs("repeat_total", "swapped_total"),
        "same_verdict_counterfactual": sum(r["repeat_proposed"] == r["swapped_proposed"] for r in rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(rows)} dossiers. Écart moyen du total : répétition {summary['mean_abs_total_change_repeat']}, "
          f"contrefactuel {summary['mean_abs_total_change_counterfactual']} ; même verdict après changement de pays : "
          f"{summary['same_verdict_counterfactual']}/{len(rows)}. Écrit dans {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
