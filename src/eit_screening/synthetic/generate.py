"""Génère une cohorte de dossiers fictifs sur le disque.

Pour chaque candidat :

- ``application.pdf``           dossier au format de l'export SurveyMonkey Apply ;
- ``reference.json``            données exactes ayant servi à fabriquer le PDF ;
- ``personal_statement.txt``    transcription de la vidéo de présentation ;
- ``assessment_reflection.txt`` transcription de la vidéo de réflexion.

Et pour la cohorte :

- ``assessment_results.csv``    export de la plateforme de test ;
- ``scenarios.csv``             niveau et anomalie de chaque dossier, connus par construction.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .profiles import ANOMALIES, Dossier, build_cohort
from .render_pdf import render_dossier

ASSESSMENT_COLUMNS = [
    "first_name", "last_name", "email", "score_percent", "time_taken_minutes", "completed_at",
]
SCENARIO_COLUMNS = [
    "application_id", "niveau", "anomalie", "description", "eligible_attendu",
    "score_test", "duree_test_minutes", "email_test",
]


def write_cohort(dossiers: list[Dossier], out_dir: str | Path) -> Path:
    """Écrit tous les fichiers d'une cohorte et renvoie le dossier de sortie."""
    out_dir = Path(out_dir)
    for dossier in dossiers:
        app = dossier.application
        folder = out_dir / "dossiers" / app.application_id
        folder.mkdir(parents=True, exist_ok=True)
        app.form_page_count = render_dossier(dossier, folder / "application.pdf")
        (folder / "reference.json").write_text(app.model_dump_json(indent=2), encoding="utf-8")
        (folder / "personal_statement.txt").write_text(dossier.personal_statement + "\n", encoding="utf-8")
        (folder / "assessment_reflection.txt").write_text(dossier.reflection + "\n", encoding="utf-8")

    with (out_dir / "assessment_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ASSESSMENT_COLUMNS)
        writer.writeheader()
        # Triées par nom : l'ordre de l'export ne trahit pas celui des dossiers.
        rows = [dossier.assessment for dossier in dossiers if dossier.assessment]
        writer.writerows(sorted(rows, key=lambda row: (row["last_name"].lower(), row["first_name"].lower())))

    with (out_dir / "scenarios.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCENARIO_COLUMNS)
        writer.writeheader()
        for dossier in dossiers:
            code = dossier.scenario.anomalies[0] if dossier.scenario.anomalies else ""
            row = dossier.assessment or {}
            writer.writerow(
                {
                    "application_id": dossier.application.application_id,
                    "niveau": dossier.scenario.tier,
                    "anomalie": code,
                    "description": ANOMALIES.get(code, ""),
                    "eligible_attendu": "oui" if dossier.scenario.expected_eligible else "non",
                    "score_test": row.get("score_percent", ""),
                    "duree_test_minutes": row.get("time_taken_minutes", ""),
                    # Adresse de la ligne du candidat dans l'export du test : vérité
                    # connue par construction, pour mesurer l'appariement.
                    "email_test": row.get("email", ""),
                }
            )
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génère des dossiers de candidature fictifs.")
    parser.add_argument("-n", "--nombre", type=int, default=40, help="Nombre de dossiers (défaut : 40)")
    parser.add_argument("--graine", type=int, default=2026, help="Graine aléatoire, pour un résultat reproductible")
    parser.add_argument("-o", "--out", type=Path, default=Path("data/fictifs"), help="Dossier de sortie")
    args = parser.parse_args(argv)

    dossiers = build_cohort(args.nombre, args.graine)
    out_dir = write_cohort(dossiers, args.out)
    anomalies = sum(1 for dossier in dossiers if dossier.scenario.anomalies)
    print(f"{len(dossiers)} dossiers écrits dans {out_dir} ({anomalies} avec une anomalie).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
