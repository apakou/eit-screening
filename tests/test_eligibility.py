"""Contrôles d'éligibilité : constats attendus sur les dossiers fictifs, et cas limites."""

from datetime import date, datetime
from functools import cache

import pytest

from eit_screening.screening.eligibility import (
    SCENARIO_CODES,
    age_on,
    check_eligibility,
    compare_with_scenarios,
    load_config,
    main,
)
from eit_screening.synthetic import content as C
from eit_screening.synthetic.profiles import build_cohort

CONFIG = load_config()


@cache
def _regular_application():
    return next(d.application for d in build_cohort(10, seed=2026) if not d.scenario.anomalies)


def _application(**personal):
    """Dossier fictif régulier dont on modifie quelques champs personnels."""
    app = _regular_application().model_copy(deep=True)
    for name, value in personal.items():
        setattr(app.personal, name, value)
    return app


def _graduating(*dates):
    """Dossier régulier dont les formations sont obtenues aux dates données."""
    app = _application()
    template = app.education[0]
    app.education = [template.model_copy(update={"graduation_date": d}) for d in dates]
    return app


def _config(**age):
    config = CONFIG.model_copy(deep=True)
    for name, value in age.items():
        setattr(config.age, name, value)
    return config


def _set_answer(app, key, value):
    for answer in app.eligibility:
        if answer.key == key:
            answer.answer = value
            return app
    raise AssertionError(key)


def _codes(report):
    return [finding.code for finding in report.findings]


# --- Critère d'acceptation : cohorte de référence, lue depuis les PDF ---------


def test_reference_cohort_from_pdf(cohort, parsed):
    out_dir, dossiers = cohort
    reports = [check_eligibility(parsed[d.application.application_id]) for d in dossiers]
    flagged = {report.application_id: _codes(report) for report in reports if report.findings}
    expected = {
        d.application.application_id: [SCENARIO_CODES[c] for c in d.scenario.anomalies if c in SCENARIO_CODES]
        for d in dossiers
        if any(c in SCENARIO_CODES for c in d.scenario.anomalies)
    }
    assert flagged == expected
    # Composition de la cohorte (feuille de route) : 2 âges hors tranche, 1 âge limite,
    # 1 nationalité hors zone, 1 diplôme en 2028, 1 diplôme en 2027.
    assert len(flagged) == 6

    comparison = compare_with_scenarios(reports, out_dir / "scenarios.csv")
    assert (comparison.expected, comparison.found) == (6, 6)
    assert comparison.missed == [] and comparison.false_alerts == []
    assert comparison.dossiers_without_finding == comparison.clean_dossiers == 34


def test_findings_quote_the_pdf(cohort, parsed):
    _, dossiers = cohort
    for dossier in dossiers:
        if not dossier.scenario.has("age_out_of_range"):
            continue
        app = parsed[dossier.application.application_id]
        (finding,) = check_eligibility(app).findings
        assert finding.severity == "alert"
        quoted = {item.field: item.value for item in finding.evidence}
        # Citations brutes de l'export, pas des valeurs reformatées.
        assert quoted["eligibility.age_in_range"] == "Yes"
        assert quoted["personal.date_of_birth"] == next(i.answer for i in app.items if i.question.casefold() == "date of birth")


@pytest.mark.parametrize("seed", [1, 7, 42, 2025, 2026])
def test_only_eligibility_anomalies_are_flagged(seed):
    for dossier in build_cohort(40, seed=seed):
        report = check_eligibility(dossier.application, CONFIG)
        expected = [SCENARIO_CODES[c] for c in dossier.scenario.anomalies if c in SCENARIO_CODES]
        assert _codes(report) == expected, dossier.application.application_id


def test_cli_with_scenarios(cohort, tmp_path, capsys):
    out_dir, _ = cohort
    out = tmp_path / "constats.json"
    assert main([str(out_dir / "dossiers"), "--scenarios", str(out_dir / "scenarios.csv"), "-o", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "attendues : 6, retrouvées : 6, manquées : 0, constats en trop : 0" in printed
    assert out.exists()


# --- Âge ----------------------------------------------------------------------


def test_age_on():
    reference = date(2026, 1, 1)
    assert age_on(date(2005, 1, 1), reference) == 21  # anniversaire le jour même
    assert age_on(date(2005, 1, 2), reference) == 20  # anniversaire le lendemain
    assert age_on(date(1995, 1, 1), reference) == 31
    assert age_on(date(1995, 1, 2), reference) == 30
    assert age_on(date(2004, 2, 29), date(2025, 2, 28)) == 20


@pytest.mark.parametrize(
    ("birth", "flagged"),
    [
        (date(2006, 1, 1), False),  # 21 ans pile au 1er janvier 2027
        (date(2006, 1, 2), True),  # 20 ans au 1er janvier 2027
        (date(1991, 1, 2), False),  # 35 ans, 36 le lendemain
        (date(1991, 1, 1), True),  # 36 ans pile
    ],
)
def test_age_bounds(birth, flagged):
    report = check_eligibility(_application(date_of_birth=birth), CONFIG)
    assert ("age_out_of_range" in _codes(report)) is flagged


def _submitted(app, day):
    app.last_submitted = datetime(day.year, day.month, day.day, 12, 0)
    return app


def test_twenty_at_submission_but_twenty_one_at_reference_is_flagged_not_excluded():
    app = _submitted(_application(date_of_birth=date(2005, 10, 1)), date(2026, 7, 10))
    (finding,) = check_eligibility(app, CONFIG).findings
    assert (finding.code, finding.severity) == ("age_borderline", "to_check")
    assert "20 when the application was submitted" in finding.message


def test_twenty_one_at_submission_is_not_flagged():
    app = _submitted(_application(date_of_birth=date(2005, 3, 1)), date(2026, 7, 10))
    assert check_eligibility(app, CONFIG).findings == []


def test_thirty_five_is_flagged_while_programme_end_is_unknown():
    (finding,) = check_eligibility(_application(date_of_birth=date(1991, 6, 1)), CONFIG).findings
    assert (finding.code, finding.severity) == ("age_borderline", "to_check")


def test_thirty_five_against_a_known_programme_end():
    config = _config(program_end=date(2027, 3, 31))
    assert check_eligibility(_application(date_of_birth=date(1991, 6, 1)), config).findings == []
    (finding,) = check_eligibility(_application(date_of_birth=date(1991, 2, 1)), config).findings
    assert finding.code == "age_borderline" and "36 at programme end" in finding.message


def test_twenty_at_reference_but_twenty_one_at_a_known_start():
    app = _application(date_of_birth=date(2006, 2, 1))
    assert _codes(check_eligibility(app, CONFIG)) == ["age_out_of_range"]
    (finding,) = check_eligibility(app, _config(program_start=date(2027, 3, 1))).findings
    assert (finding.code, finding.severity) == ("age_borderline", "to_check")


def test_missing_birth_date_is_to_check():
    report = check_eligibility(_application(date_of_birth=None), CONFIG)
    assert [(f.code, f.severity) for f in report.findings] == [("age_unknown", "to_check")]
    assert report.age is None


def test_age_no_answer_consistent_with_data():
    app = _set_answer(_application(date_of_birth=date(1990, 6, 1)), "age_in_range", False)
    (finding,) = check_eligibility(app, CONFIG).findings
    assert finding.code == "age_out_of_range"
    assert "No" in finding.message



def test_no_answer_kept_when_birth_date_missing():
    app = _set_answer(_application(date_of_birth=None), "age_in_range", False)
    assert _codes(check_eligibility(app, CONFIG)) == ["age_unknown", "eligibility_answer_no"]


def test_no_answer_kept_when_citizenship_missing():
    app = _set_answer(_application(country_of_citizenship=None), "citizen_of_region", False)
    assert _codes(check_eligibility(app, CONFIG)) == ["citizenship_unknown", "eligibility_answer_no"]


def test_evidence_without_form_items_still_quotes_answer():
    # Dossier construit en mémoire (pas d'``items``) : la réponse « No » reste citée.
    (finding,) = check_eligibility(_set_answer(_application(), "can_relocate", False), CONFIG).findings
    assert finding.evidence[0].value == "No"

# --- Nationalité --------------------------------------------------------------


def test_every_generator_country_is_classified():
    for country in C.COUNTRIES:
        assert CONFIG.citizenship.in_zone(country), country
    for country in C.OUTSIDE_REGION:
        assert CONFIG.citizenship.in_zone(country) is None, country


@pytest.mark.parametrize(
    "spelling", ["Cote d'Ivoire", "CÔTE D’IVOIRE", "Ivory Coast", "Gambia", "the gambia", "Guinea-Bissau", "Sénégal"]
)
def test_country_spellings(spelling):
    assert CONFIG.citizenship.in_zone(spelling)


def test_similar_names_stay_distinct():
    assert CONFIG.citizenship.in_zone("Equatorial Guinea") is None
    assert CONFIG.citizenship.in_zone("Papua New Guinea") is None


@pytest.mark.parametrize("country", ["Kenya", "Rwanda", "Uganda", "Tanzania", "Ethiopia", "Ghana", "Togo"])
def test_west_and_east_africa_are_in_zone(country):
    assert check_eligibility(_application(country_of_citizenship=country), CONFIG).findings == []


@pytest.mark.parametrize("country", ["Cameroon", "Democratic Republic of the Congo", "South Africa", "Egypt"])
def test_outside_west_and_east_africa(country):
    (finding,) = check_eligibility(_application(country_of_citizenship=country), CONFIG).findings
    assert (finding.code, finding.severity) == ("citizenship_outside_region", "alert")


def test_dual_citizenship_lowers_severity():
    app = _application(country_of_citizenship="Cameroon", dual_citizenship=True)
    (finding,) = check_eligibility(app, CONFIG).findings
    assert (finding.code, finding.severity) == ("citizenship_outside_region", "to_check")


def test_missing_citizenship_is_to_check():
    (finding,) = check_eligibility(_application(country_of_citizenship=None), CONFIG).findings
    assert (finding.code, finding.severity) == ("citizenship_unknown", "to_check")


def test_residence_is_not_citizenship():
    # Résider hors zone ne compte pas : seule la nationalité est contrôlée.
    app = _application(country_of_residence="Cameroon", based_in="Other")
    assert check_eligibility(app, CONFIG).findings == []


# --- Diplôme --------------------------------------------------------------------


def test_graduation_in_2028_is_excluded():
    (finding,) = check_eligibility(_graduating(date(2028, 6, 30)), CONFIG).findings
    assert (finding.code, finding.severity) == ("graduation_after_cutoff", "alert")


def test_graduation_in_2027_is_flagged_with_its_month():
    (finding,) = check_eligibility(_graduating(date(2027, 9, 15)), CONFIG).findings
    assert (finding.code, finding.severity) == ("graduation_review", "to_check")
    assert "Sep 2027" in finding.message


def test_graduation_before_2027_is_fine():
    assert check_eligibility(_graduating(date(2026, 12, 31)), CONFIG).findings == []


def test_latest_degree_counts():
    (finding,) = check_eligibility(_graduating(date(2022, 6, 1), date(2028, 1, 15)), CONFIG).findings
    assert finding.code == "graduation_after_cutoff" and "latest of the degrees" in finding.message
    assert finding.evidence[0].field == "education[1].graduation_date"


# --- Réponses d'éligibilité ---------------------------------------------------


def test_every_no_answer_is_flagged():
    app = _set_answer(_set_answer(_application(), "can_relocate", False), "communal_housing", False)
    report = check_eligibility(app, CONFIG)
    assert _codes(report) == ["eligibility_answer_no", "eligibility_answer_no"]
    assert {f.evidence[0].field for f in report.findings} == {
        "eligibility.can_relocate", "eligibility.communal_housing"
    }


def test_no_to_age_question_despite_age_in_range():
    app = _set_answer(_application(date_of_birth=date(2000, 6, 1)), "age_in_range", False)
    (finding,) = check_eligibility(app, CONFIG).findings
    assert finding.code == "eligibility_answer_no"
    assert "is 26 on 1 Jan 2027" in finding.message


def test_unreadable_answer_is_to_check():
    app = _set_answer(_application(), "software_experience", None)
    (finding,) = check_eligibility(app, CONFIG).findings
    assert (finding.code, finding.severity) == ("eligibility_answer_unreadable", "to_check")


def test_no_eligibility_answers():
    app = _application()
    app.eligibility = []
    assert _codes(check_eligibility(app, CONFIG)) == ["eligibility_answers_missing"]


def test_report_has_no_decision_field():
    fields = set(check_eligibility(_application(), CONFIG).model_dump())
    assert fields == {"application_id", "age", "citizenship", "findings"}


# --- Paramètres ---------------------------------------------------------------

# Règles du formulaire 2026, avant le guide 2027 : 21-30 ans, Afrique de l'Ouest seulement.
FORM_2026_CONFIG = """
[age]
min = 21
max = 30
reference_date = 2026-01-01

[citizenship]
zone_name = "Afrique de l'Ouest"
countries = ["Ghana", "Nigeria", "Togo"]
"""


def test_alternate_config_changes_results(tmp_path):
    path = tmp_path / "formulaire-2026.toml"
    path.write_text(FORM_2026_CONFIG, encoding="utf-8")
    config = load_config(path)
    app = _application(country_of_citizenship="Kenya", date_of_birth=date(1993, 3, 1))
    assert check_eligibility(app, CONFIG).findings == []
    assert _codes(check_eligibility(app, config)) == ["age_out_of_range", "citizenship_outside_region"]


def test_invalid_age_range(tmp_path):
    path = tmp_path / "invalide.toml"
    path.write_text(FORM_2026_CONFIG.replace("max = 30", "max = 18"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)

