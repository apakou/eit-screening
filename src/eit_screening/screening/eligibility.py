"""Contrôles d'éligibilité d'un dossier de candidature.

Le module confronte les réponses du candidat aux questions d'éligibilité avec
les données de son dossier (date de naissance, nationalité, date d'obtention du
diplôme) et relève chaque réponse « No ». Il produit des **constats**, jamais une décision : un constat
dit ce qui pose question et cite l'élément du dossier qui le montre ;
l'évaluateur tranche.

Les messages des constats sont en anglais : ils s'affichent sur la plateforme
des évaluateurs de MEST. Les sorties de la ligne de commande restent en français.

Les paramètres (tranche d'âge, date de référence, pays de la zone, années
d'obtention du diplôme) viennent d'un fichier TOML. Le fichier par défaut,
``eligibility.toml``, suit le guide d'évaluation 2027 ; un autre fichier peut
être passé avec ``--config``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tomllib
from datetime import date, datetime
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .. import __version__
from ..models import Application, EligibilityAnswer, FormItem
from .common import SEVERITY_LABELS, Evidence, Finding, day, git_commit, month, plain_text

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


class AgeRule(BaseModel):
    min: int
    max: int
    reference_date: date
    # Démarrage et fin du programme : facultatifs (le guide 2027 ne les donne pas).
    program_start: date | None = None
    program_end: date | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> AgeRule:
        if self.min > self.max:
            raise ValueError(f"Tranche d'âge invalide : {self.min} > {self.max}")
        return self


class CitizenshipRule(BaseModel):
    zone_name: str
    countries: list[str]
    aliases: dict[str, str] = Field(default_factory=dict)

    def in_zone(self, country: str) -> str | None:
        """Nom du pays tel qu'écrit dans la configuration s'il est dans la zone, sinon ``None``."""
        key = normalize_country(country)
        for name in self.countries:
            if normalize_country(name) == key:
                return name
        for alias, name in self.aliases.items():
            if normalize_country(alias) == key and name in self.countries:
                return name
        return None


class EducationRule(BaseModel):
    excluded_from_year: int
    review_year: int


class QuestionKeys(BaseModel):
    """Clés des questions d'éligibilité reliées à une donnée du dossier."""

    age: str = "age_in_range"
    citizenship: str = "citizen_of_region"


class EligibilityConfig(BaseModel):
    age: AgeRule
    citizenship: CitizenshipRule
    education: EducationRule | None = None
    questions: QuestionKeys = Field(default_factory=QuestionKeys)


DEFAULT_CONFIG = "eligibility.toml"


def load_config(path: Path | str | None = None) -> EligibilityConfig:
    """Lit la configuration ; sans chemin, prend le fichier livré avec le module."""
    if path is None:
        raw = resources.files(__package__).joinpath(DEFAULT_CONFIG).read_bytes()
    else:
        raw = Path(path).read_bytes()
    return EligibilityConfig.model_validate(tomllib.loads(raw.decode("utf-8")))


def normalize_country(name: str) -> str:
    """Forme comparable d'un nom de pays : sans accents, sans casse, sans « The » initial."""
    return re.sub(r"^the ", "", plain_text(name))


# --------------------------------------------------------------------------
# Constats
# --------------------------------------------------------------------------


class EligibilityReport(BaseModel):
    """Constats d'éligibilité d'un dossier. Ne contient aucune décision."""

    application_id: str
    age: int | None = None
    citizenship: str | None = None
    findings: list[Finding] = Field(default_factory=list)


def age_on(birth: date, reference: date) -> int:
    """Âge révolu à la date de référence."""
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def _same_question(left: str | None, right: str | None) -> bool:
    def norm(text: str | None) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().casefold()).replace("’", "'")

    return norm(left) == norm(right)


def _form_item(app: Application, question: str, eligibility_task: bool) -> FormItem | None:
    """Question et réponse telles qu'elles sont écrites dans l'export (``None`` si absentes).

    ``eligibility_task`` choisit l'étape : questions d'éligibilité, ou formulaire principal.
    """
    for item in app.items:
        in_eligibility = "eligibility" in (item.task or "").casefold()
        if in_eligibility == eligibility_task and _same_question(item.question, question):
            return item
    return None


def _yes_no(value: bool | None) -> str | None:
    return {True: "Yes", False: "No"}.get(value)


def _personal_evidence(app: Application, field: str, question: str, fallback: str | None) -> Evidence:
    item = _form_item(app, question, eligibility_task=False)
    if item is None:
        return Evidence(field=f"personal.{field}", question=question, value=fallback)
    return Evidence(field=f"personal.{field}", question=item.question, value=item.answer)


def _eligibility_evidence(app: Application, answer: EligibilityAnswer) -> Evidence:
    """Citation de la réponse à une question d'éligibilité."""
    field = f"eligibility.{answer.key}" if answer.key else "eligibility"
    item = _form_item(app, answer.question, eligibility_task=True)
    value = item.answer if item is not None else _yes_no(answer.answer)
    return Evidence(field=field, question=answer.question, value=value)


def _answer_evidence(app: Application, key: str) -> tuple[Evidence | None, bool | None]:
    """Réponse du candidat à la question d'éligibilité ``key``, avec sa citation."""
    for answer in app.eligibility:
        if answer.key == key:
            return _eligibility_evidence(app, answer), answer.answer
    return None, None


def _declared(answer: bool | None) -> str:
    if answer is True:
        return "although the applicant answered “Yes” to the eligibility question"
    if answer is False:
        return "as the applicant's “No” to the eligibility question confirms"
    return "and the applicant's answer to the eligibility question is missing or unreadable"


def _check_age(app: Application, rule: AgeRule, key: str) -> tuple[int | None, Finding | None]:
    birth = app.personal.date_of_birth
    answer_evidence, answer = _answer_evidence(app, key)
    evidence = [_personal_evidence(app, "date_of_birth", "Date of birth", birth and birth.isoformat())]
    if answer_evidence:
        evidence.append(answer_evidence)
    if birth is None:
        return None, Finding(
            code="age_unknown",
            severity="to_check",
            message="Date of birth missing or unreadable: age cannot be checked.",
            evidence=evidence,
        )
    age = age_on(birth, rule.reference_date)
    reference = day(rule.reference_date)
    submitted = app.last_submitted.date() if app.last_submitted else None

    def borderline(message: str) -> tuple[int, Finding]:
        return age, Finding(code="age_borderline", severity="to_check", message=message, evidence=evidence)

    if age == rule.min - 1 and rule.program_start and age_on(birth, rule.program_start) >= rule.min:
        return borderline(
            f"{age} on {reference}, but {rule.min} at programme start ({day(rule.program_start)}): "
            "flagged for review, not excluded."
        )
    if age == rule.min and submitted and age_on(birth, submitted) < rule.min:
        return borderline(
            f"{age_on(birth, submitted)} when the application was submitted ({day(submitted)}), {age} on {reference}: "
            "within range on the reference date; flagged for review."
        )
    if age == rule.max:
        if rule.program_end is None:
            return borderline(
                f"{age} on {reference}: may turn {age + 1} during the programme; flagged for review."
            )
        if age_on(birth, rule.program_end) > rule.max:
            return borderline(
                f"{age} on {reference}, {age_on(birth, rule.program_end)} at programme end "
                f"({day(rule.program_end)}); flagged for review."
            )
    if rule.min <= age <= rule.max:
        return age, None
    return age, Finding(
        code="age_out_of_range",
        severity="alert",
        message=(
            f"{age} on {reference}, outside the {rule.min}–{rule.max} age range, {_declared(answer)}."
        ),
        evidence=evidence,
    )


def _check_citizenship(app: Application, rule: CitizenshipRule, key: str) -> Finding | None:
    person = app.personal
    answer_evidence, answer = _answer_evidence(app, key)
    evidence = [
        _personal_evidence(app, "country_of_citizenship", "Country of citizenship", person.country_of_citizenship)
    ]
    if answer_evidence:
        evidence.append(answer_evidence)
    if not person.country_of_citizenship:
        return Finding(
            code="citizenship_unknown",
            severity="to_check",
            message="Citizenship missing or unreadable: the eligible region cannot be checked.",
            evidence=evidence,
        )
    if rule.in_zone(person.country_of_citizenship):
        return None
    message = (
        f"Declared citizenship “{person.country_of_citizenship}” is outside {rule.zone_name}, {_declared(answer)}."
    )
    if person.dual_citizenship:
        # Le formulaire ne donne pas la seconde nationalité : elle peut être dans la zone.
        evidence.append(
            _personal_evidence(app, "dual_citizenship", "Do you have dual citizenship?", "Yes")
        )
        return Finding(
            code="citizenship_outside_region",
            severity="to_check",
            message=message + " The applicant declares dual citizenship; the application does not say which.",
            evidence=evidence,
        )
    return Finding(code="citizenship_outside_region", severity="alert", message=message, evidence=evidence)


def _check_education(app: Application, rule: EducationRule) -> Finding | None:
    """Date d'obtention du diplôme : la plus tardive des formations déclarées."""
    dated = [(edu.graduation_date, index) for index, edu in enumerate(app.education) if edu.graduation_date]
    if not dated:
        return None
    latest, index = max(dated)
    raw = [i.answer for i in app.items
           if "eligibility" not in (i.task or "").casefold() and _same_question(i.question, "Graduation date")]
    value = raw[index] if index < len(raw) else latest.isoformat()
    evidence = [Evidence(field=f"education[{index}].graduation_date", question="Graduation date", value=value)]
    several = " (latest of the degrees declared)" if len(dated) > 1 else ""
    if latest.year >= rule.excluded_from_year:
        return Finding(
            code="graduation_after_cutoff",
            severity="alert",
            message=f"Graduation in {month(latest)}{several}: from {rule.excluded_from_year}, "
            "the evaluation guide excludes the application.",
            evidence=evidence,
        )
    if latest.year == rule.review_year:
        return Finding(
            code="graduation_review",
            severity="to_check",
            message=f"Graduation in {month(latest)}{several}: {rule.review_year} graduates are flagged; check the month.",
            evidence=evidence,
        )
    return None


def check_eligibility(app: Application, config: EligibilityConfig | None = None) -> EligibilityReport:
    """Contrôle un dossier et renvoie ses constats (liste vide si rien n'est relevé)."""
    config = config or load_config()
    keys = config.questions
    findings: list[Finding] = []

    age, age_finding = _check_age(app, config.age, keys.age)
    citizenship_finding = _check_citizenship(app, config.citizenship, keys.citizenship)
    # Une question dont la réponse figure déjà dans un constat hors tranche ou hors
    # zone n'est pas relevée deux fois. Si la donnée manque, un « No » reste relevé.
    covered = set()
    for key, finding in ((keys.age, age_finding), (keys.citizenship, citizenship_finding)):
        if finding is not None:
            findings.append(finding)
            if finding.code in ("age_out_of_range", "citizenship_outside_region"):
                covered.add(key)

    if config.education is not None:
        education_finding = _check_education(app, config.education)
        if education_finding is not None:
            findings.append(education_finding)

    if not app.eligibility:
        findings.append(
            Finding(
                code="eligibility_answers_missing",
                severity="to_check",
                message="No answers to the eligibility questions were found in the application.",
            )
        )

    for answer in app.eligibility:
        if answer.key is not None and answer.key in covered:
            continue
        if answer.answer is True:
            continue
        evidence = [_eligibility_evidence(app, answer)]
        if answer.answer is False:
            message = f"Answered “No” to the eligibility question “{answer.question}”."
            if answer.key == keys.age and age is not None:
                message += f" Yet the applicant is {age} on {day(config.age.reference_date)}."
            elif answer.key == keys.citizenship and app.personal.country_of_citizenship:
                message += f" Yet the declared citizenship is “{app.personal.country_of_citizenship}”."
            findings.append(
                Finding(code="eligibility_answer_no", severity="alert", message=message, evidence=evidence)
            )
        else:
            findings.append(
                Finding(
                    code="eligibility_answer_unreadable",
                    severity="to_check",
                    message=f"Missing or unreadable answer to the eligibility question “{answer.question}”.",
                    evidence=evidence,
                )
            )

    return EligibilityReport(
        application_id=app.application_id,
        age=age,
        citizenship=app.personal.country_of_citizenship,
        findings=findings,
    )


# --------------------------------------------------------------------------
# Comparaison avec scenarios.csv (dossiers fictifs)
# --------------------------------------------------------------------------

# Anomalies de scenarios.csv que ce module doit retrouver, avec le code du constat attendu.
SCENARIO_CODES = {
    "age_out_of_range": "age_out_of_range",
    "age_borderline": "age_borderline",
    "citizenship_outside_region": "citizenship_outside_region",
    "graduation_after_cutoff": "graduation_after_cutoff",
    "graduation_review": "graduation_review",
}


class ScenarioComparison(BaseModel):
    expected: int
    found: int
    missed: list[str] = Field(default_factory=list)
    false_alerts: list[str] = Field(default_factory=list)
    clean_dossiers: int
    dossiers_without_finding: int


def compare_with_scenarios(reports: list[EligibilityReport], scenarios_csv: Path) -> ScenarioComparison:
    """Confronte les constats aux anomalies placées dans les dossiers fictifs."""
    expected: dict[str, set[str]] = {}
    with open(scenarios_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            codes = {SCENARIO_CODES[c] for c in (row.get("anomalie") or "").split(";") if c in SCENARIO_CODES}
            expected[row["application_id"]] = codes
    found, missed, false_alerts = 0, [], []
    clean = without = 0
    for report in reports:
        wanted = expected.get(report.application_id, set())
        seen = {finding.code for finding in report.findings}
        for code in sorted(wanted):
            if code in seen:
                found += 1
            else:
                missed.append(f"{report.application_id} : {code}")
        for code in sorted(seen - wanted):
            false_alerts.append(f"{report.application_id} : {code}")
        if not wanted:
            clean += 1
            without += not report.findings
    return ScenarioComparison(
        expected=sum(len(expected.get(r.application_id, set())) for r in reports),
        found=found,
        missed=missed,
        false_alerts=false_alerts,
        clean_dossiers=clean,
        dossiers_without_finding=without,
    )


# --------------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------------


def _pdf_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("application.pdf"))


def _print_table(reports: list[EligibilityReport]) -> None:
    print(f"{'Numéro':<12} {'Âge':>4}  {'Nationalité':<16} Constats")
    for report in reports:
        age = "?" if report.age is None else str(report.age)
        codes = ", ".join(
            f"{finding.code} ({SEVERITY_LABELS[finding.severity]})" for finding in report.findings
        ) or "-"
        print(f"{report.application_id:<12} {age:>4}  {(report.citizenship or '?'):<16} {codes}")
    for report in reports:
        for finding in report.findings:
            print(f"\n{report.application_id} · {finding.code} · {SEVERITY_LABELS[finding.severity]}")
            print(f"  {finding.message}")
            for item in finding.evidence:
                print(f"  - {item.question} → « {item.value} »  [{item.field}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Contrôle l'éligibilité de dossiers exportés en PDF. Produit des constats, aucune décision."
    )
    parser.add_argument("chemin", type=Path, help="Fichier application.pdf, ou dossier parcouru récursivement")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : formulaire 2026)")
    parser.add_argument("--scenarios", type=Path, help="scenarios.csv des dossiers fictifs, pour mesurer la détection")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON des constats")
    args = parser.parse_args(argv)

    from ..ingestion.smapply_pdf import parse_application

    paths = _pdf_paths(args.chemin)
    if not paths:
        print(f"Aucun fichier application.pdf trouvé dans {args.chemin}.", file=sys.stderr)
        return 1
    config = load_config(args.config)
    reports = [check_eligibility(parse_application(path), config) for path in paths]

    _print_table(reports)
    flagged = sum(1 for report in reports if report.findings)
    print(f"\n{len(reports)} dossiers contrôlés, {flagged} avec au moins un constat.")

    comparison = None
    if args.scenarios:
        comparison = compare_with_scenarios(reports, args.scenarios)
        print(
            f"Anomalies d'éligibilité attendues : {comparison.expected}, retrouvées : {comparison.found}, "
            f"manquées : {len(comparison.missed)}, constats en trop : {len(comparison.false_alerts)}."
        )
        print(
            f"Dossiers sans anomalie d'éligibilité : {comparison.clean_dossiers}, "
            f"dont {comparison.dossiers_without_finding} sans aucun constat."
        )
        for line in comparison.missed:
            print(f"  manquée : {line}")
        for line in comparison.false_alerts:
            print(f"  en trop : {line}")

    if args.out:
        export = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "code_version": __version__,
            "git_commit": git_commit(),
            "source": str(args.chemin),
            "config": config.model_dump(mode="json"),
            "comparison": comparison.model_dump() if comparison else None,
            "reports": [report.model_dump(mode="json") for report in reports],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Constats écrits dans {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
