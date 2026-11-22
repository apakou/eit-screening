"""Évaluation du prototype : un export unique des mesures, reproductible par une commande.

Rassemble les résultats écrits par chaque étape (``data/resultats``, verdicts),
les confronte à ``scenarios.csv`` (ce que le système doit retrouver, connu par
construction) et écrit ``evaluation.json`` avec la date, la version du code,
les modèles et la graine de la cohorte.

Ce que ce module ne mesure pas, faute d'évaluateurs : l'alignement avec les
décisions humaines, l'accord entre évaluateurs, le temps passé avec et sans
l'outil, le questionnaire SUS. Il le dit dans l'export plutôt que d'inventer
un chiffre. Le niveau d'un dossier fictif (fort, moyen, faible) n'est pas une
note d'évaluateur : la corrélation avec ce niveau est un contrôle de cohérence.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..privacy.leak_check import check_output
from ..screening.common import git_commit

TIER_RANK = {"faible": 1, "moyen": 2, "fort": 3}
NOT_MEASURED = [
    "Alignement : part des verdicts proposés validés sans modification (requiert des évaluateurs).",
    "Accord entre deux évaluateurs humains (plafond réaliste de l'alignement).",
    "Temps passé par dossier avec et sans l'outil, en plan croisé (lots A et B).",
    "Questionnaire SUS en fin de séance.",
    "Mesures RAGAS de pertinence et de précision du contexte jugées par un modèle (non lancées).",
]


def ranks(values: list[float]) -> list[float]:
    """Rangs moyens (ex aequo partagés), à partir de 1."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return result


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (sx * sy), 3) if sx and sy else None


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a:
        return None
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((observed - expected) / (1 - expected), 3) if expected < 1 else None


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _verdicts(folder: Path) -> dict[str, dict]:
    if not folder.exists():
        return {}
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("C-*.json")) if not p.name.endswith(".appel.json")
    }


def verdict_summary(verdicts: dict[str, dict], tiers: dict[str, str]) -> dict:
    """Conformité, citations, verdicts proposés, et cohérence avec le niveau des dossiers fictifs."""
    if not verdicts:
        return {"available": False}
    valid = [v for v in verdicts.values() if v["llm"]["schema_valid"]]
    quotes = sum(v["quotes_total"] for v in verdicts.values())
    verified = sum(v["quotes_verified"] for v in verdicts.values())
    by_tier: dict[str, list[int]] = defaultdict(list)
    pairs = []
    for pseudonym, v in verdicts.items():
        if v["total"] is not None and pseudonym in tiers:
            by_tier[tiers[pseudonym]].append(v["total"])
            pairs.append((TIER_RANK[tiers[pseudonym]], v["total"]))
    return {
        "available": True,
        "dossiers": len(verdicts),
        "schema_valid": len(valid),
        "quotes_total": quotes,
        "quotes_verified": verified,
        "quote_verification_rate": round(verified / quotes, 4) if quotes else None,
        "scores_without_quote": sum(1 for v in verdicts.values() for c in v["criteria"] if c["score"] > 0 and not c["quote"]),
        "scores_above_zero": sum(1 for v in verdicts.values() for c in v["criteria"] if c["score"] > 0),
        "proposed": dict(sorted(Counter(v["proposed"] for v in verdicts.values()).items())),
        "seconds_per_dossier": round(sum(v["llm"]["seconds"] for v in verdicts.values()) / len(verdicts), 1),
        "mean_total_by_tier": {t: round(sum(s) / len(s), 1) for t, s in sorted(by_tier.items())},
        "spearman_tier_total": spearman([p[0] for p in pairs], [p[1] for p in pairs]),
        "model": next(iter(verdicts.values()))["llm"]["model"],
    }


def anomaly_detection(scenarios: list[dict], signals: dict[str, set[str]]) -> dict:
    """Pour chaque anomalie de scenarios.csv : retrouvées, manquées, fausses alertes."""
    by_code: dict[str, set[str]] = defaultdict(set)
    for row in scenarios:
        for code in filter(None, (row["anomalie"] or "").split(";")):
            by_code[code].add(row["application_id"])
    everyone = {row["application_id"] for row in scenarios}
    result = {}
    for code in sorted(set(by_code) | set(signals)):
        expected = by_code.get(code, set())
        if code not in signals:
            result[code] = {"expected": len(expected), "covered": False}
            continue
        found = signals[code]
        result[code] = {
            "expected": len(expected),
            "covered": True,
            "found": len(expected & found),
            "missed": sorted(expected - found),
            "false_alerts": len((everyone - expected) & found),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rassemble les mesures du prototype dans un export unique.")
    parser.add_argument("--fictifs", type=Path, default=Path("data/fictifs"))
    parser.add_argument("--resultats", type=Path, default=Path("data/resultats"))
    parser.add_argument("--anonymises", type=Path, default=Path("data/anonymises"))
    parser.add_argument("--verdicts", type=Path, default=Path("data/verdicts"))
    parser.add_argument("--verdicts-sans-recherche", type=Path, default=Path("data/verdicts-dossier-entier"))
    parser.add_argument("--table", type=Path, required=True, help="Table de correspondance")
    parser.add_argument("--graine", type=int, default=2026, help="Graine de la cohorte fictive")
    parser.add_argument("-o", "--out", type=Path, default=Path("data/resultats/evaluation.json"))
    args = parser.parse_args(argv)

    entries = json.loads(args.table.expanduser().read_text(encoding="utf-8"))["entries"]
    to_id = {pseudonym: app_id for app_id, pseudonym in entries.items()}
    with open(args.fictifs / "scenarios.csv", newline="", encoding="utf-8") as handle:
        scenarios = list(csv.DictReader(handle))
    tiers = {entries[r["application_id"]]: r["niveau"] for r in scenarios if r["application_id"] in entries}
    out = args.resultats

    eligibility = _read(out / "eligibilite.json")
    assessment = _read(out / "appariement.json")
    extraction = _read(out / "extraction.json")
    indexing = _read(out / "indexation.json")
    search = _read(out / "recherche.json")
    rag = _verdicts(args.verdicts)
    full = _verdicts(args.verdicts_sans_recherche)

    # Signaux par anomalie : quel constat compte comme « retrouvé ».
    signals: dict[str, set[str]] = defaultdict(set)
    if eligibility:
        for report in eligibility["reports"]:
            for finding in report["findings"]:
                signals[finding["code"]].add(report["application_id"])
    if assessment:
        for match in assessment["result"]["matches"]:
            for finding in match["findings"]:
                signals[finding["code"]].add(match["application_id"])
            if match["method"] == "swapped_name":
                signals["assessment_name_swapped"].add(match["application_id"])
    if rag:
        signals["generic_ai_answers"] = {
            to_id[p] for p, v in rag.items() if p in to_id and any(c["key"] == "generic_ai_responses" for c in v["concerns"])
        }
    keep = {"age_out_of_range", "citizenship_outside_region", "assessment_not_found", "assessment_late",
            "assessment_too_fast", "assessment_name_swapped", "generic_ai_answers"}
    detection = anomaly_detection(scenarios, {k: v for k, v in signals.items() if k in keep})

    leaks = []
    for app_id, pseudonym in sorted(entries.items()):
        reference = args.fictifs / "dossiers" / app_id / "reference.json"
        anonymized = args.anonymises / f"{pseudonym}.json"
        if reference.exists() and anonymized.exists():
            leaks.append(check_output(json.loads(reference.read_text(encoding="utf-8")),
                                      json.loads(anonymized.read_text(encoding="utf-8")), anonymized.name))

    agreement = None
    common = sorted(set(rag) & set(full))
    if common:
        a = [rag[p]["proposed"] for p in common]
        b = [full[p]["proposed"] for p in common]
        agreement = {
            "dossiers": len(common),
            "same_verdict": round(sum(x == y for x, y in zip(a, b)) / len(common), 4),
            "cohen_kappa": cohen_kappa(a, b),
        }

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_commit": git_commit(),
        "seed": args.graine,
        "dossiers": len(scenarios),
        "models": {
            "embedding": indexing and indexing.get("embedding_model"),
            "reranking": search and search.get("reranking_model"),
            "ocr": extraction and extraction.get("ocr_engine"),
            "transcription": extraction and extraction.get("whisper_model"),
            "verdict": rag and next(iter(rag.values()))["llm"]["model"],
        },
        "anomaly_detection": detection,
        "eligibility": eligibility and eligibility.get("comparison"),
        "assessment_matching": assessment and assessment.get("comparison"),
        "anonymization": {
            "dossiers": len(leaks),
            "identity_leaks": sum(bool(c.identity_leaks) for c in leaks),
            "declared_places_in_free_text": sum(bool(c.declared_places) for c in leaks),
            "dossiers_with_suspect_words": sum(bool(c.suspects) for c in leaks),
        },
        "ocr": extraction and {k: v for k, v in extraction.items() if k.startswith("certificates")},
        "indexing": indexing and {**indexing["report"], "located": indexing["location_check"]["located"]},
        "retrieval": search and {
            "modes": search["evaluation"]["modes"],
            "strict_modes": search["evaluation"]["strict_modes"],
            "random_hit_at_3": search["evaluation"]["random_hit_at_3"],
            "candidates_recall": search["evaluation"]["candidates_recall"],
        },
        "verdict_rag": verdict_summary(rag, tiers),
        "verdict_full_dossier": verdict_summary(full, tiers),
        "verdict_agreement_rag_vs_full_dossier": agreement,
        "not_measured": NOT_MEASURED,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Évaluation du {report['generated_at']} — code {report['git_commit']}, graine {args.graine}, "
          f"{report['dossiers']} dossiers.\n")
    print("Anomalies de scenarios.csv :")
    for code, d in detection.items():
        if d["covered"]:
            print(f"  {code:<28} {d['found']}/{d['expected']} retrouvées, {d['false_alerts']} fausse(s) alerte(s)")
        else:
            print(f"  {code:<28} {d['expected']} attendue(s) — aucun contrôle ne la cherche")
    a = report["anonymization"]
    print(f"\nAnonymisation : fuites d'identité {a['identity_leaks']}/{a['dossiers']}, lieu déclaré dans le texte "
          f"{a['declared_places_in_free_text']}/{a['dossiers']}, mot suspect {a['dossiers_with_suspect_words']}/{a['dossiers']}.")
    if report["retrieval"]:
        print("Recherche (bon passage dans les 3 premiers) : " + ", ".join(
            f"{m} {s['hit_at_3']:.1%}" for m, s in report["retrieval"]["modes"].items()))
    for label, key in (("Verdicts avec recherche", "verdict_rag"), ("Verdicts dossier entier", "verdict_full_dossier")):
        v = report[key]
        if not v["available"]:
            print(f"{label} : non produits.")
            continue
        rate = v["quote_verification_rate"]
        print(f"{label} ({v['model']}) : {v['schema_valid']}/{v['dossiers']} conformes, citations vérifiées "
              f"{v['quotes_verified']}/{v['quotes_total']}" + (f" ({rate:.1%})" if rate is not None else "")
              + f", {v['seconds_per_dossier']} s/dossier, total moyen par niveau {v['mean_total_by_tier']}, "
              f"Spearman niveau-total {v['spearman_tier_total']}.")
        print(f"  verdicts proposés : {v['proposed']} ; notes > 0 sans citation : "
              f"{v['scores_without_quote']}/{v['scores_above_zero']}")
    if agreement:
        print(f"Accord des deux variantes : {agreement['same_verdict']:.1%} (kappa {agreement['cohen_kappa']}).")
    print("\nNon mesuré (requiert des évaluateurs) :")
    for line in NOT_MEASURED:
        print(f"  - {line}")
    print(f"\nExport écrit dans {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
