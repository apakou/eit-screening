"""Cohorte fictive partagée par les tests : générée une seule fois par session."""

import gc

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


@pytest.fixture(scope="session")
def anonymized_cohort(cohort, parsed):
    """Cohorte anonymisée en mémoire (sans reconnaissance d'entités, pour aller vite)."""
    from eit_screening.privacy.anonymize import anonymize_dossier, load_config, read_transcripts

    out_dir, dossiers = cohort
    config = load_config()
    config.ner.enabled = False
    result = []
    for number, dossier in enumerate(dossiers):
        app_id = dossier.application.application_id
        anonymized, _ = anonymize_dossier(
            parsed[app_id], f"C-{number:08X}", read_transcripts(out_dir / "dossiers" / app_id), config
        )
        result.append(anonymized)
    return result


@pytest.fixture(autouse=True, scope="module")
def _release_heavy_models():
    """Libère Docling, Whisper, bge-m3 et le re-ranking après chaque fichier de tests.

    Ensemble, ils dépassent la mémoire libre de la machine de développement.
    """
    yield
    from eit_screening.media import attachments, transcribe
    from eit_screening.search import embed, rerank

    attachments._converter.cache_clear()
    transcribe._model.cache_clear()
    embed._load.cache_clear()
    rerank._load.cache_clear()
    gc.collect()
