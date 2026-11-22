"""Aller-retour : un dossier fictif relu par le module d'import redonne ses données."""

import pytest

from eit_screening.ingestion.smapply_pdf import parse_application
from eit_screening.synthetic.profiles import ANOMALIES, build_cohort

# Champs comparés un à un entre la référence et le dossier relu.
FIELDS = [
    "application_id", "applicant_display_name", "applicant_email", "program", "last_submitted",
    "labels", "tasks", "eligibility", "personal", "education", "experience", "essays",
    "uploads", "evidence_urls", "references", "form_page_count",
]


def test_every_dossier_roundtrips(cohort, parsed):
    _, dossiers = cohort
    for dossier in dossiers:
        reference = dossier.application
        expected, actual = reference.model_dump(), parsed[reference.application_id].model_dump()
        for name in FIELDS:
            assert actual[name] == expected[name], f"{reference.application_id} : champ {name}"


def test_attachments_and_warnings(cohort, parsed):
    _, dossiers = cohort
    for dossier in dossiers:
        app_id = dossier.application.application_id
        app = parsed[app_id]
        expected_pages = (dossier.resume is not None) + len(dossier.certificates)
        assert len(app.attachment_pages) == expected_pages, app_id
        # Un certificat sur deux est une image : il doit être signalé pour l'OCR.
        expected_ocr = sum(certificate.as_image for certificate in dossier.certificates)
        assert sum(page.needs_ocr for page in app.attachment_pages) == expected_ocr, app_id
        if dossier.scenario.has("missing_resume"):
            assert any("Fichier non fourni" in warning for warning in app.warnings), app_id
        else:
            assert app.warnings == [], f"{app_id} : {app.warnings}"


def test_cohort_covers_every_anomaly(cohort):
    _, dossiers = cohort
    seen = {code for dossier in dossiers for code in dossier.scenario.anomalies}
    assert seen == set(ANOMALIES)
    assert sum(1 for dossier in dossiers if dossier.scenario.anomalies) == 16


def test_essays_respect_word_limit():
    for seed in range(5):
        for dossier in build_cohort(40, seed=seed):
            for essay in dossier.application.essays:
                assert 0 < essay.word_count <= 100, essay.answer


def test_same_seed_same_cohort():
    first = [d.application.model_dump() for d in build_cohort(10, seed=7)]
    second = [d.application.model_dump() for d in build_cohort(10, seed=7)]
    assert first == second


@pytest.mark.parametrize("application_id", ["EIT-2027-001001", "0000001001"])
def test_identifier_formats(tmp_path, application_id):
    """Identifiants du guide 2027 (EIT-2027-XXXXXX) et anciens identifiants à 10 chiffres."""
    from eit_screening.synthetic.render_pdf import render_dossier

    dossier = build_cohort(1, seed=3)[0]
    dossier.application.application_id = application_id
    render_dossier(dossier, tmp_path / "application.pdf")
    assert parse_application(tmp_path / "application.pdf").application_id == application_id


def test_generated_identifiers_follow_the_guide():
    import re

    ids = [d.application.application_id for d in build_cohort(40, seed=2026)]
    assert all(re.fullmatch(r"EIT-2027-\d{6}", i) for i in ids) and len(set(ids)) == 40
