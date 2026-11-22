"""Cohorte fictive partagée par les tests : générée une seule fois par session."""

import pytest

from eit_screening.ingestion.smapply_pdf import parse_application
from eit_screening.synthetic.generate import write_cohort
from eit_screening.synthetic.profiles import build_cohort


@pytest.fixture(scope="session")
def cohort(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("fictifs")
    dossiers = build_cohort(40, seed=2026)
    write_cohort(dossiers, out_dir)
    return out_dir, dossiers


@pytest.fixture(scope="session")
def parsed(cohort):
    """Dossiers de la cohorte relus depuis leur PDF, par numéro (la lecture est l'étape lente)."""
    out_dir, dossiers = cohort
    return {
        d.application.application_id: parse_application(
            out_dir / "dossiers" / d.application.application_id / "application.pdf"
        )
        for d in dossiers
    }
