"""Appariement avec l'export du test : cohorte de référence, autres graines, cas construits à la main."""

from datetime import datetime

import pytest

from eit_screening.models import Application, Personal
from eit_screening.screening.assessment_match import (
    AssessmentRow,
    compare_with_scenarios,
    load_config,
    main,
    match_assessments,
    read_export,
)
from eit_screening.synthetic.profiles import build_cohort

CONFIG = load_config()


def _app(application_id, first, last, email):
    return Application(
        application_id=application_id, personal=Personal(first_name=first, last_name=last, email=email)
    )


def _row(line, first, last, email, score=60, minutes=50, completed="2025-07-20T10:00"):
    raw = {
        "first_name": first, "last_name": last, "email": email,
        "score_percent": str(score), "time_taken_minutes": str(minutes), "completed_at": completed or "",
    }
    return AssessmentRow(
        line=line, first_name=first, last_name=last, email=email, score_percent=score,
        time_taken_minutes=minutes, completed_at=datetime.fromisoformat(completed) if completed else None, raw=raw,
    )


def _rows_from(dossiers):
    rows = [d.assessment for d in dossiers if d.assessment]
    return [
        _row(i + 2, r["first_name"], r["last_name"], r["email"], r["score_percent"],
             r["time_taken_minutes"], r["completed_at"])
        for i, r in enumerate(rows)
    ]


def _by_id(result):
    return {match.application_id: match for match in result.matches}


def _codes(match):
    return [finding.code for finding in match.findings]


# --- Critère d'acceptation : cohorte de référence, dossiers lus depuis les PDF --


def test_reference_cohort(cohort, parsed):
    out_dir, dossiers = cohort
    rows = read_export(out_dir / "assessment_results.csv")
    assert len(rows) == 38
    result = match_assessments([parsed[d.application.application_id] for d in dossiers], rows)
    comparison = compare_with_scenarios(result, rows, out_dir / "scenarios.csv")
    assert comparison.correctly_attached == 38
    assert comparison.wrongly_attached == [] and comparison.not_attached == []
    assert (comparison.swapped_attached, comparison.swapped_expected) == (2, 2)
    assert comparison.findings_expected == comparison.findings_found == {
        "assessment_not_found": 2, "assessment_late": 2, "assessment_too_fast": 2,
    }
    assert comparison.missed == [] and comparison.false_alerts == []
    assert result.unattached == []

    # Chaque ligne va au dossier dont elle vient (vérité connue par construction).
    matches = _by_id(result)
    for dossier in dossiers:
        match = matches[dossier.application.application_id]
        if dossier.assessment is None:
            assert match.row is None
        else:
            assert match.row.email == dossier.assessment["email"]


def test_cli(cohort, tmp_path, capsys):
    out_dir, _ = cohort
    out = tmp_path / "appariement.json"
    args = [str(out_dir / "dossiers"), str(out_dir / "assessment_results.csv"),
            "--scenarios", str(out_dir / "scenarios.csv"), "-o", str(out)]
    assert main(args) == 0
    printed = capsys.readouterr().out
    assert "Lignes rattachées au bon dossier : 38/38, au mauvais : 0, non rattachées : 0." in printed
    assert "Noms inversés rattachés : 2/2." in printed
    assert out.exists()


# --- Autres graines : jamais de rattachement erroné ----------------------------


@pytest.mark.parametrize("seed", range(12))
def test_never_attaches_to_wrong_dossier(seed):
    dossiers = build_cohort(40, seed=seed)
    rows = _rows_from(dossiers)
    result = match_assessments([d.application for d in dossiers], rows, CONFIG)
    truth = {d.assessment["email"]: d.application.application_id for d in dossiers if d.assessment}
    for match in result.matches:
        if match.row is not None:
            assert truth[match.row.email] == match.application_id, (seed, match.row.line)
    for dossier in dossiers:
        match = _by_id(result)[dossier.application.application_id]
        if dossier.scenario.has("assessment_not_found"):
            # Introuvable, ou à vérifier si une ligne ambiguë pourrait être la sienne.
            assert match.row is None
            assert {"assessment_not_found", "assessment_match_ambiguous"} & set(_codes(match))
        for code in ("assessment_late", "assessment_too_fast"):
            if dossier.scenario.has(code) and match.row is not None:
                assert code in _codes(match)


def test_totals_over_twelve_seeds():
    """Chiffre repris dans la feuille de route : 12 graines, 456 lignes."""
    rows_total = attached = wrong = ambiguous = orphans = 0
    for seed in range(12):
        dossiers = build_cohort(40, seed=seed)
        rows = _rows_from(dossiers)
        result = match_assessments([d.application for d in dossiers], rows, CONFIG)
        truth = {d.assessment["email"]: d.application.application_id for d in dossiers if d.assessment}
        rows_total += len(rows)
        for match in result.matches:
            if match.row is not None:
                attached += 1
                wrong += truth[match.row.email] != match.application_id
        ambiguous += sum(item.reason == "ambiguous" for item in result.unattached)
        orphans += sum(item.reason == "no_candidate" for item in result.unattached)
    # Les 3 lignes refusées : nom inversé d'un candidat qui a un homonyme exact.
    assert (rows_total, attached, wrong, ambiguous, orphans) == (456, 453, 0, 3, 0)


def test_row_order_does_not_matter():
    dossiers = build_cohort(40, seed=2026)
    apps = [d.application for d in dossiers]
    rows = _rows_from(dossiers)
    forward = match_assessments(apps, rows, CONFIG)
    backward = match_assessments(apps, list(reversed(rows)), CONFIG)
    assert forward.model_dump() == backward.model_dump()


# --- Niveaux d'appariement ---------------------------------------------------


def test_email_ignores_case():
    result = match_assessments(
        [_app("1", "Ama", "Osei", "ama.osei@example.org")],
        [_row(2, "A.", "O.", "AMA.Osei@Example.org ")],
        CONFIG,
    )
    assert result.matches[0].method == "email"


def test_swapped_name():
    result = match_assessments(
        [_app("1", "Sika", "Kone", "sika@example.org"), _app("2", "Yaw", "Mensah", "yaw@example.org")],
        [_row(2, "Kone", "Sika", "kone.s@example.net")],
        CONFIG,
    )
    assert _by_id(result)["1"].method == "swapped_name"
    assert _by_id(result)["2"].row is None


def test_similar_name_ignores_accents_and_case():
    result = match_assessments(
        [_app("1", "Kouamé", "Koné", "k@example.org")],
        [_row(2, "KOUAME", "kone", "autre@example.net")],
        CONFIG,
    )
    match = result.matches[0]
    assert (match.method, match.similarity) == ("similar_name", 100.0)


def test_name_below_threshold_is_not_attached():
    result = match_assessments(
        [_app("1", "Emeka", "Okonkwo", "e@example.org")],
        [_row(2, "Amaka", "Okonkwo", "a@example.net")],
        CONFIG,
    )
    assert result.matches[0].row is None
    assert _codes(result.matches[0]) == ["assessment_not_found"]
    (orphan,) = result.unattached
    assert orphan.reason == "no_candidate"


# --- Ambiguïtés : refuser plutôt que deviner -----------------------------------


def test_homonyms_are_refused():
    apps = [_app("1", "Kwesi", "Mensah", "k1@example.org"), _app("2", "Kwesi", "Mensah", "k2@example.org")]
    result = match_assessments(apps, [_row(2, "Kwesi", "Mensah", "kwesi@example.net")], CONFIG)
    for match in result.matches:
        assert match.row is None
        assert _codes(match) == ["assessment_match_ambiguous"]
    (row,) = result.unattached
    assert (row.reason, row.candidates) == ("ambiguous", ["1", "2"])
    # Le message ne nomme pas l'autre candidat.
    assert "Mensah" not in result.matches[0].findings[0].message


def test_homonym_without_test_is_not_given_the_other_ones():
    # Cas de la cohorte de référence : deux homonymes, un seul a passé le test.
    apps = [_app("1", "Kwesi", "Mensah", "k1@example.org"), _app("2", "Kwesi", "Mensah", "k2@example.org")]
    result = match_assessments(apps, [_row(2, "Kwesi", "Mensah", "k1@example.org")], CONFIG)
    assert _by_id(result)["1"].method == "email"
    assert _by_id(result)["2"].row is None
    assert _codes(_by_id(result)["2"]) == ["assessment_not_found"]


def test_near_names_are_refused():
    # « Femi » et « Temi » Balogun : 92/100 de ressemblance, deux personnes différentes.
    apps = [_app("1", "Femi", "Balogun", "f@example.org"), _app("2", "Temi", "Balogun", "t@example.org")]
    result = match_assessments(apps, [_row(2, "Balogun", "Femi", "fb@example.net")], CONFIG)
    assert all(match.row is None for match in result.matches)
    assert result.unattached[0].reason == "ambiguous"


def test_shared_email_is_refused():
    apps = [_app("1", "Ama", "Osei", "shared@example.org"), _app("2", "Esi", "Owusu", "shared@example.org")]
    result = match_assessments(apps, [_row(2, "Ama", "Osei", "shared@example.org")], CONFIG)
    assert all(match.row is None for match in result.matches)


# --- Constats ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("completed", "late"),
    [("2025-08-10T23:59", False), ("2025-08-11T00:00", True), ("2025-07-01T09:00", False)],
)
def test_deadline_day_included(completed, late):
    result = match_assessments(
        [_app("1", "Ama", "Osei", "a@example.org")], [_row(2, "Ama", "Osei", "a@example.org", completed=completed)],
        CONFIG,
    )
    assert ("assessment_late" in _codes(result.matches[0])) is late


@pytest.mark.parametrize(("minutes", "flagged"), [(20, False), (19.5, True), (7, True), (70, False)])
def test_duration_threshold(minutes, flagged):
    result = match_assessments(
        [_app("1", "Ama", "Osei", "a@example.org")], [_row(2, "Ama", "Osei", "a@example.org", minutes=minutes)],
        CONFIG,
    )
    match = result.matches[0]
    assert ("assessment_too_fast" in _codes(match)) is flagged
    if flagged:
        (finding,) = match.findings
        assert finding.severity == "to_check"
        assert {e.question for e in finding.evidence} == {"time_taken_minutes", "score_percent"}
        assert all(e.source == "assessment_results.csv, ligne 2" for e in finding.evidence)


def test_unreadable_date():
    result = match_assessments(
        [_app("1", "Ama", "Osei", "a@example.org")], [_row(2, "Ama", "Osei", "a@example.org", completed=None)],
        CONFIG,
    )
    assert _codes(result.matches[0]) == ["assessment_date_unreadable"]


def test_multiple_results_keep_the_earliest():
    rows = [
        _row(2, "Ama", "Osei", "a@example.org", completed="2025-08-12T10:00"),
        _row(3, "Ama", "Osei", "a@example.org", completed="2025-07-12T10:00"),
    ]
    match = match_assessments([_app("1", "Ama", "Osei", "a@example.org")], rows, CONFIG).matches[0]
    assert (match.row.line, match.other_rows) == (3, [2])
    assert _codes(match) == ["assessment_multiple_results"]


def test_not_found_cites_the_dossier():
    app = build_cohort(10, seed=2026)[0].application
    (finding,) = match_assessments([app], [], CONFIG).matches[0].findings
    assert finding.code == "assessment_not_found" and finding.severity == "alert"
    assert {e.field for e in finding.evidence} == {"personal.email", "tasks"}


# --- Lecture de l'export et paramètres ----------------------------------------

OTHER_FORMAT = """
[export]
delimiter = ";"
datetime_format = "%d/%m/%Y %H:%M"

[export.columns]
first_name = "First Name"
last_name = "Last Name"
email = "Email"
score_percent = "Score"
time_taken_minutes = "Minutes"
completed_at = "Completed"

[deadline]
last_day = 2025-07-31

[duration]
allotted_minutes = 70
min_minutes = 30

[matching]
name_threshold = 95
"""


def test_other_export_format(tmp_path):
    config_path = tmp_path / "autre.toml"
    config_path.write_text(OTHER_FORMAT, encoding="utf-8")
    config = load_config(config_path)
    export = tmp_path / "export.csv"
    export.write_text(
        "First Name;Last Name;Email;Score;Minutes;Completed\n"
        "Ama;Osei;a@example.org;71%;25;05/08/2025 14:30\n",
        encoding="utf-8",
    )
    (row,) = read_export(export, config)
    assert (row.line, row.score_percent, row.completed_at) == (2, 71.0, datetime(2025, 8, 5, 14, 30))
    match = match_assessments([_app("1", "Ama", "Osei", "a@example.org")], [row], config).matches[0]
    # Même ligne : en retard et trop rapide avec ces paramètres, pas avec ceux par défaut.
    assert _codes(match) == ["assessment_late", "assessment_too_fast"]
    assert match_assessments([_app("1", "Ama", "Osei", "a@example.org")], [row], CONFIG).matches[0].findings == []


def test_missing_column(tmp_path):
    export = tmp_path / "export.csv"
    export.write_text("first_name,last_name,email\nAma,Osei,a@example.org\n", encoding="utf-8")
    with pytest.raises(ValueError, match="score_percent"):
        read_export(export, CONFIG)
