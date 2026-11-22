"""Appariement des dossiers avec l'export de la plateforme de test.

Chaque ligne de l'export est rattachée à un dossier, à trois niveaux :

1. adresse e-mail identique (sans tenir compte de la casse) ;
2. prénom et nom inversés ;
3. nom complet ressemblant au-dessus d'un seuil, sans casse ni accents.

Une ligne qui pourrait appartenir à deux dossiers n'est rattachée à aucun :
le module refuse de deviner et le signale. Chaque ligne est examinée contre
tous les dossiers, indépendamment des autres lignes : le résultat ne dépend
pas de l'ordre de l'export.

Une fois les lignes rattachées, le module relève pour chaque dossier les
constats suivants : test introuvable, test passé après la date limite, durée
anormalement courte, plusieurs résultats, rattachement ambigu. Ce sont des
constats, jamais des décisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tomllib
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from rapidfuzz import fuzz

from .. import __version__
from ..models import Application
from .common import SEVERITY_LABELS, Evidence, Finding, git_commit, plain_text

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


class ExportColumns(BaseModel):
    """Noms des colonnes de l'export. Une chaîne vide : colonne absente de cet export."""

    first_name: str = "first_name"
    last_name: str = "last_name"
    email: str = "email"
    duration: str = "duration"
    completed_at: str = "completed_at"
    # Score : une fiche ClassMarker porte les points obtenus, le total et le
    # pourcentage. Le pourcentage est déduit des points quand sa colonne manque.
    score_percent: str = "score_percent"
    score_points: str = ""
    score_max: str = ""

    @property
    def declared(self) -> list[str]:
        """Colonnes annoncées par la configuration, donc attendues dans l'export."""
        return [name for name in self.model_dump().values() if name]


class ExportFormat(BaseModel):
    delimiter: str = ","
    encoding: str = "utf-8"
    datetime_format: str = ""
    timezone: str = "UTC"
    columns: ExportColumns = Field(default_factory=ExportColumns)


class DeadlineRule(BaseModel):
    deadline: datetime  # avec fuseau horaire
    platform_close: datetime | None = None

    @model_validator(mode="after")
    def _aware(self) -> DeadlineRule:
        if self.deadline.tzinfo is None:
            raise ValueError("La date limite du test doit préciser son fuseau horaire (ex. 2026-07-20T23:59:59Z).")
        return self


class DurationRule(BaseModel):
    allotted_minutes: float
    min_minutes: float


class MatchingRule(BaseModel):
    name_threshold: float = Field(ge=0, le=100)


class TestStructure(BaseModel):
    """Structure du test, relevée sur une fiche de résultat ClassMarker."""

    total_points: float | None = None
    categories: list[str] = Field(default_factory=list)


class AssessmentConfig(BaseModel):
    export: ExportFormat = Field(default_factory=ExportFormat)
    deadline: DeadlineRule
    duration: DurationRule
    matching: MatchingRule
    test: TestStructure = Field(default_factory=TestStructure)


DEFAULT_CONFIG = "assessment.toml"


def load_config(path: Path | str | None = None) -> AssessmentConfig:
    """Lit la configuration ; sans chemin, prend le fichier livré avec le module."""
    if path is None:
        raw = resources.files(__package__).joinpath(DEFAULT_CONFIG).read_bytes()
    else:
        raw = Path(path).read_bytes()
    return AssessmentConfig.model_validate(tomllib.loads(raw.decode("utf-8")))


# --------------------------------------------------------------------------
# Lecture de l'export
# --------------------------------------------------------------------------


class AssessmentRow(BaseModel):
    """Ligne de l'export du test. ``raw`` garde les cellules telles qu'écrites."""

    line: int
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    score_percent: float | None = None
    score_points: float | None = None
    score_max: float | None = None
    time_taken_minutes: float | None = None
    completed_at: datetime | None = None
    raw: dict[str, str] = Field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)


def _number(text: str | None) -> float | None:
    text = (text or "").strip().rstrip("%").replace(",", ".").strip()
    try:
        return float(text)
    except ValueError:
        return None


# Formats relevés sur une fiche de résultat ClassMarker de la promotion 2027 :
#     Points: 46 / 50     Duration: 00:38:06     Date finished: Tue 21 Jul '26 5:52pm
CLASSMARKER_FORMAT = "classmarker"

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1
    )
}

_CLASSMARKER_DATE = re.compile(
    r"^(?:[A-Za-z]{3},?\s+)?(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3})[a-z]*\s+'?(?P<year>\d{4}|\d{2})"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<meridiem>[AaPp]\.?[Mm]\.?)?)?$"
)

_DURATION = re.compile(r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{2})$")


def _classmarker_datetime(text: str) -> datetime | None:
    """Lit « Tue 21 Jul '26 5:52pm ».

    Les noms de jour et de mois sont lus en anglais, sans dépendre de la langue
    de la machine : ``strptime`` et ses codes ``%a`` et ``%b`` suivent la locale.
    """
    match = _CLASSMARKER_DATE.match(text)
    if match is None:
        return None
    month = _MONTHS.get(match["month"].lower())
    if month is None:
        return None
    year = int(match["year"])
    if len(match["year"]) == 2:
        year += 2000
    hour, minute = int(match["hour"] or 0), int(match["minute"] or 0)
    meridiem = (match["meridiem"] or "").replace(".", "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    try:
        return datetime(year, month, int(match["day"]), hour, minute)
    except ValueError:
        return None


def _duration_minutes(text: str | None) -> float | None:
    """Durée en minutes. Accepte « hh:mm:ss », « mm:ss » ou un nombre de minutes."""
    text = (text or "").strip()
    if not text:
        return None
    match = _DURATION.match(text)
    if match is None:
        return _number(text)
    return int(match["hours"] or 0) * 60 + int(match["minutes"]) + int(match["seconds"]) / 60


def _datetime(text: str | None, fmt: str) -> datetime | None:
    """Date de l'export : ``classmarker``, vide (ISO 8601) ou codes strftime."""
    text = (text or "").strip()
    if not text:
        return None
    if fmt == CLASSMARKER_FORMAT:
        return _classmarker_datetime(text)
    try:
        return datetime.strptime(text, fmt) if fmt else datetime.fromisoformat(text)
    except ValueError:
        return None


def read_export(path: Path | str, config: AssessmentConfig | None = None) -> list[AssessmentRow]:
    """Lit l'export du test. Le numéro de ligne compte l'en-tête comme ligne 1."""
    config = config or load_config()
    fmt, columns = config.export, config.export.columns
    rows: list[AssessmentRow] = []
    with open(path, newline="", encoding=fmt.encoding) as handle:
        reader = csv.DictReader(handle, delimiter=fmt.delimiter)
        missing = [name for name in columns.declared if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Colonnes absentes de l'export du test : {', '.join(missing)}")
        for record in reader:
            raw = {key: (value or "") for key, value in record.items() if key is not None}

            def cell(column: str, source: dict[str, str] = raw) -> str:
                """Cellule d'une colonne ; chaîne vide si la colonne n'est pas déclarée."""
                return source.get(column, "") if column else ""

            points = _number(cell(columns.score_points))
            maximum = _number(cell(columns.score_max)) or config.test.total_points
            percent = _number(cell(columns.score_percent))
            if percent is None and points is not None and maximum:
                percent = round(points / maximum * 100, 2)
            rows.append(
                AssessmentRow(
                    line=reader.line_num,
                    first_name=cell(columns.first_name).strip() or None,
                    last_name=cell(columns.last_name).strip() or None,
                    email=cell(columns.email).strip() or None,
                    score_percent=percent,
                    score_points=points,
                    score_max=maximum,
                    time_taken_minutes=_duration_minutes(cell(columns.duration)),
                    completed_at=_datetime(cell(columns.completed_at), fmt.datetime_format),
                    raw=raw,
                )
            )
    return rows


# --------------------------------------------------------------------------
# Rattachement des lignes
# --------------------------------------------------------------------------

MatchMethod = Literal["email", "swapped_name", "similar_name"]
METHOD_LABELS: dict[str, str] = {
    "email": "e-mail",
    "swapped_name": "nom inversé",
    "similar_name": "nom ressemblant",
}


class _Candidate:
    def __init__(self, app: Application) -> None:
        person = app.personal
        self.application_id = app.application_id
        self.emails = {e.strip().casefold() for e in (person.email, app.applicant_email) if e and e.strip()}
        self.first = plain_text(person.first_name)
        self.last = plain_text(person.last_name)
        self.full = " ".join(p for p in (self.first, self.last) if p) or plain_text(app.applicant_display_name)


class _Attribution(BaseModel):
    candidates: list[str]
    method: MatchMethod | None = None
    similarity: float | None = None
    best_similarity: float | None = None


def _attribute(row: AssessmentRow, candidates: list[_Candidate], threshold: float) -> _Attribution:
    """Dossiers possibles pour une ligne : un seul si le rattachement est sûr."""
    email = (row.email or "").strip().casefold()
    if email:
        hits = [c.application_id for c in candidates if email in c.emails]
        if hits:
            return _Attribution(candidates=hits, method="email" if len(hits) == 1 else None)

    first, last = plain_text(row.first_name), plain_text(row.last_name)
    full = " ".join(p for p in (first, last) if p)
    if not full:
        return _Attribution(candidates=[])
    scored = [(c, fuzz.token_sort_ratio(full, c.full)) for c in candidates if c.full]
    best = max((score for _, score in scored), default=None)
    above = [(c, score) for c, score in scored if score >= threshold]
    if len(above) != 1:
        return _Attribution(candidates=[c.application_id for c, _ in above], best_similarity=best)
    candidate, score = above[0]
    swapped = (first, last) == (candidate.last, candidate.first) and (first, last) != (candidate.first, candidate.last)
    return _Attribution(
        candidates=[candidate.application_id],
        method="swapped_name" if swapped else "similar_name",
        similarity=round(score, 1),
        best_similarity=best,
    )


class AssessmentMatch(BaseModel):
    """Résultat de test rattaché à un dossier, et constats qui en découlent."""

    application_id: str
    row: AssessmentRow | None = None
    method: MatchMethod | None = None
    similarity: float | None = None
    other_rows: list[int] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class UnattachedRow(BaseModel):
    """Ligne de l'export rattachée à aucun dossier."""

    row: AssessmentRow
    reason: Literal["no_candidate", "ambiguous"]
    candidates: list[str] = Field(default_factory=list)
    message: str


class MatchingResult(BaseModel):
    matches: list[AssessmentMatch]
    unattached: list[UnattachedRow] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Constats
# --------------------------------------------------------------------------


def _source(export_name: str, row: AssessmentRow) -> str:
    return f"{export_name}, ligne {row.line}"


def _cell(row: AssessmentRow, field: str, column: str, export_name: str) -> Evidence:
    return Evidence(
        field=f"assessment.{field}", question=column, value=row.raw.get(column), source=_source(export_name, row)
    )


def _row_identity(row: AssessmentRow, columns: ExportColumns, export_name: str) -> list[Evidence]:
    return [
        _cell(row, "first_name", columns.first_name, export_name),
        _cell(row, "last_name", columns.last_name, export_name),
        _cell(row, "email", columns.email, export_name),
    ]


def _assessment_task(app: Application) -> Evidence | None:
    """Étape « test » du dossier, telle que l'affiche SurveyMonkey Apply."""
    for task in app.tasks:
        title = task.title.casefold()
        if "assessment" in title and "reflection" not in title:
            value = " ".join(p for p in (task.status, task.completed_on and task.completed_on.isoformat()) if p)
            return Evidence(field="tasks", question=task.title, value=value or None)
    return None


def _dossier_email(app: Application) -> Evidence:
    """Adresse e-mail du dossier, avec le libellé de la question tel qu'écrit dans le PDF."""
    for item in app.items:
        if "eligibility" not in (item.task or "").casefold() and (item.question or "").strip().casefold() == "email":
            return Evidence(field="personal.email", question=item.question, value=item.answer)
    return Evidence(field="personal.email", question="Email", value=app.personal.email)


def _row_findings(row: AssessmentRow, config: AssessmentConfig, export_name: str) -> list[Finding]:
    columns = config.export.columns
    findings: list[Finding] = []
    deadline = config.deadline.deadline
    completed = _cell(row, "completed_at", columns.completed_at, export_name)
    finished = row.completed_at
    if finished is not None and finished.tzinfo is None:
        finished = finished.replace(tzinfo=ZoneInfo(config.export.timezone))
    if row.completed_at is None:
        findings.append(
            Finding(
                code="assessment_date_unreadable",
                severity="to_check",
                message="Date de fin du test absente ou illisible : le respect de la date limite ne peut pas être contrôlé.",
                evidence=[completed],
            )
        )
    elif finished > deadline:
        gmt = finished.astimezone(timezone.utc)
        findings.append(
            Finding(
                code="assessment_late",
                severity="to_check",
                message=(
                    f"Test soumis le {gmt:%d/%m/%Y à %H:%M} GMT, après la date limite du "
                    f"{deadline.astimezone(timezone.utc):%d/%m/%Y à %H:%M} GMT."
                ),
                evidence=[completed],
            )
        )

    duration = _cell(row, "duration", columns.duration, export_name)
    score = _cell(row, "score_percent", columns.score_percent or columns.score_points, export_name)
    rule = config.duration
    if row.time_taken_minutes is None:
        findings.append(
            Finding(
                code="assessment_duration_unreadable",
                severity="to_check",
                message="Durée du test absente ou illisible.",
                evidence=[duration],
            )
        )
    elif row.time_taken_minutes < rule.min_minutes:
        score_text = "illisible" if row.score_percent is None else f"{row.score_percent:g} %"
        findings.append(
            Finding(
                code="assessment_too_fast",
                severity="to_check",
                message=(
                    f"Test terminé en {row.time_taken_minutes:.1f} minutes sur {rule.allotted_minutes:g} prévues "
                    f"(seuil : {rule.min_minutes:g} minutes), avec un score de {score_text}."
                ),
                evidence=[duration, score],
            )
        )
    return findings


def match_assessments(
    applications: list[Application],
    rows: list[AssessmentRow],
    config: AssessmentConfig | None = None,
    export_name: str = "assessment_results.csv",
) -> MatchingResult:
    """Rattache les lignes de l'export aux dossiers et relève les constats de chaque dossier."""
    config = config or load_config()
    columns = config.export.columns
    candidates = [_Candidate(app) for app in applications]

    attached: dict[str, list[tuple[AssessmentRow, _Attribution]]] = defaultdict(list)
    ambiguous_for: dict[str, list[AssessmentRow]] = defaultdict(list)
    unattached: list[UnattachedRow] = []
    for row in rows:
        attribution = _attribute(row, candidates, config.matching.name_threshold)
        if attribution.method is not None:
            attached[attribution.candidates[0]].append((row, attribution))
        elif attribution.candidates:
            for application_id in attribution.candidates:
                ambiguous_for[application_id].append(row)
            unattached.append(
                UnattachedRow(
                    row=row,
                    reason="ambiguous",
                    candidates=sorted(attribution.candidates),
                    message=(
                        f"{len(attribution.candidates)} dossiers possibles : rattachement refusé, "
                        "à trancher par un évaluateur."
                    ),
                )
            )
        else:
            best = attribution.best_similarity
            unattached.append(
                UnattachedRow(
                    row=row,
                    reason="no_candidate",
                    message=(
                        "Aucun dossier ne correspond (ni l'e-mail, ni le nom"
                        + (f" ; ressemblance la plus forte : {best:.0f}/100" if best is not None else "")
                        + ")."
                    ),
                )
            )

    matches: list[AssessmentMatch] = []
    for app in applications:
        match = AssessmentMatch(application_id=app.application_id)
        own = sorted(
            attached.get(app.application_id, []),
            key=lambda item: (item[0].completed_at or datetime.max, item[0].line),
        )
        if own:
            row, attribution = own[0]
            match.row, match.method, match.similarity = row, attribution.method, attribution.similarity
            match.other_rows = [other.line for other, _ in own[1:]]
            match.findings.extend(_row_findings(row, config, export_name))
            if match.other_rows:
                match.findings.append(
                    Finding(
                        code="assessment_multiple_results",
                        severity="to_check",
                        message=(
                            f"{len(own)} lignes de l'export correspondent à ce dossier ; "
                            f"la plus ancienne (ligne {row.line}) est retenue pour les contrôles."
                        ),
                        evidence=[e for other, _ in own for e in _row_identity(other, columns, export_name)],
                    )
                )
        for row in ambiguous_for.get(app.application_id, []):
            match.findings.append(
                Finding(
                    code="assessment_match_ambiguous",
                    severity="to_check",
                    message=(
                        f"La ligne {row.line} de l'export pourrait correspondre à ce dossier comme à un autre : "
                        "elle n'a été rattachée à aucun des deux."
                    ),
                    evidence=_row_identity(row, columns, export_name),
                )
            )
        if not own and app.application_id not in ambiguous_for:
            evidence = [_dossier_email(app)]
            task = _assessment_task(app)
            if task:
                evidence.append(task)
            match.findings.append(
                Finding(
                    code="assessment_not_found",
                    severity="alert",
                    message="Aucune ligne de l'export du test ne correspond à ce dossier (ni l'e-mail, ni le nom).",
                    evidence=evidence,
                )
            )
        matches.append(match)

    unattached.sort(key=lambda item: item.row.line)
    return MatchingResult(matches=matches, unattached=unattached)


# --------------------------------------------------------------------------
# Comparaison avec scenarios.csv (dossiers fictifs)
# --------------------------------------------------------------------------

# Anomalies de scenarios.csv que ce module doit retrouver, avec le constat attendu.
SCENARIO_CODES = {
    "assessment_not_found": "assessment_not_found",
    "assessment_late": "assessment_late",
    "assessment_too_fast": "assessment_too_fast",
}


class ScenarioComparison(BaseModel):
    export_rows: int
    correctly_attached: int
    wrongly_attached: list[str] = Field(default_factory=list)
    not_attached: list[str] = Field(default_factory=list)
    swapped_expected: int
    swapped_attached: int
    findings_expected: dict[str, int]
    findings_found: dict[str, int]
    missed: list[str] = Field(default_factory=list)
    false_alerts: list[str] = Field(default_factory=list)


def compare_with_scenarios(
    result: MatchingResult, rows: list[AssessmentRow], scenarios_csv: Path | str
) -> ScenarioComparison:
    """Confronte l'appariement à la vérité connue par construction (colonne ``email_test``)."""
    truth: dict[str, str] = {}
    anomalies: dict[str, str] = {}
    with open(scenarios_csv, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            if "email_test" not in record:
                raise ValueError("scenarios.csv sans colonne email_test : régénérer la cohorte avec eit-generate.")
            anomalies[record["application_id"]] = record.get("anomalie") or ""
            if record["email_test"]:
                truth[record["email_test"].casefold()] = record["application_id"]

    owner = {}
    for match in result.matches:
        if match.row is not None:
            owner[match.row.line] = match.application_id
    correct, wrong, missing = 0, [], []
    for row in rows:
        expected = truth.get((row.email or "").casefold())
        got = owner.get(row.line)
        if got is None and expected is None:
            correct += 1  # ligne sans dossier, laissée à juste titre sans rattachement
        elif got is None:
            missing.append(f"ligne {row.line} (attendue : {expected or 'aucun dossier'})")
        elif got == expected:
            correct += 1
        else:
            wrong.append(f"ligne {row.line} : rattachée à {got}, attendue {expected or 'aucun dossier'}")

    swapped = {aid for aid, code in anomalies.items() if code == "assessment_name_swapped"}
    swapped_ok = sum(
        1 for m in result.matches if m.application_id in swapped and m.method == "swapped_name"
        and m.row is not None and owner.get(m.row.line) == m.application_id
        and truth.get((m.row.email or "").casefold()) == m.application_id
    )

    expected_codes = {code: 0 for code in SCENARIO_CODES.values()}
    found_codes = {code: 0 for code in SCENARIO_CODES.values()}
    missed, false_alerts = [], []
    for match in result.matches:
        wanted = {SCENARIO_CODES[anomalies.get(match.application_id, "")]} if anomalies.get(
            match.application_id
        ) in SCENARIO_CODES else set()
        seen = {finding.code for finding in match.findings}
        for code in wanted:
            expected_codes[code] += 1
            if code in seen:
                found_codes[code] += 1
            else:
                missed.append(f"{match.application_id} : {code}")
        for code in sorted(seen - wanted):
            false_alerts.append(f"{match.application_id} : {code}")

    return ScenarioComparison(
        export_rows=len(rows),
        correctly_attached=correct,
        wrongly_attached=wrong,
        not_attached=missing,
        swapped_expected=len(swapped),
        swapped_attached=swapped_ok,
        findings_expected=expected_codes,
        findings_found=found_codes,
        missed=missed,
        false_alerts=false_alerts,
    )


# --------------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------------


def _print_result(result: MatchingResult) -> None:
    print(f"{'Numéro':<12} {'Ligne':>5}  {'Méthode':<16} {'Score':>5} {'Durée':>5}  {'Terminé le':<16} Constats")
    for match in result.matches:
        row = match.row
        method = METHOD_LABELS.get(match.method or "", "-")
        if match.method == "similar_name":
            method += f" {match.similarity:g}"
        codes = ", ".join(f"{f.code} ({SEVERITY_LABELS[f.severity]})" for f in match.findings) or "-"
        if row is None:
            print(f"{match.application_id:<12} {'-':>5}  {method:<16} {'-':>5} {'-':>5}  {'-':<16} {codes}")
            continue
        score = "?" if row.score_percent is None else f"{row.score_percent:g}"
        # Les durées de l'export sont au format hh:mm:ss : arrondies ici à la minute près.
        minutes = "?" if row.time_taken_minutes is None else f"{row.time_taken_minutes:.1f}"
        done = row.completed_at.strftime("%d/%m/%Y %H:%M") if row.completed_at else "?"
        print(f"{match.application_id:<12} {row.line:>5}  {method:<16} {score:>5} {minutes:>5}  {done:<16} {codes}")
    for match in result.matches:
        for finding in match.findings:
            print(f"\n{match.application_id} · {finding.code} · {SEVERITY_LABELS[finding.severity]}")
            print(f"  {finding.message}")
            for item in finding.evidence:
                where = f"  ({item.source})" if item.source else ""
                print(f"  - {item.question} → « {item.value} »{where}")
    for item in result.unattached:
        print(f"\nLigne {item.row.line} non rattachée ({item.reason}) : {item.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rattache l'export du test aux dossiers PDF et relève les constats. Aucune décision."
    )
    parser.add_argument("dossiers", type=Path, help="Fichier application.pdf, ou dossier parcouru récursivement")
    parser.add_argument("export", type=Path, help="Export de la plateforme de test (CSV)")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : assessment.toml)")
    parser.add_argument("--scenarios", type=Path, help="scenarios.csv des dossiers fictifs, pour mesurer le résultat")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON des résultats")
    args = parser.parse_args(argv)

    from ..ingestion.smapply_pdf import parse_application

    paths = [args.dossiers] if args.dossiers.is_file() else sorted(args.dossiers.rglob("application.pdf"))
    if not paths:
        print(f"Aucun fichier application.pdf trouvé dans {args.dossiers}.", file=sys.stderr)
        return 1
    config = load_config(args.config)
    rows = read_export(args.export, config)
    applications = [parse_application(path) for path in paths]
    result = match_assessments(applications, rows, config, export_name=args.export.name)

    _print_result(result)
    attached = sum(1 for m in result.matches if m.row is not None)
    flagged = sum(1 for m in result.matches if m.findings)
    print(
        f"\n{len(applications)} dossiers, {len(rows)} lignes dans l'export : {attached} dossiers avec un test, "
        f"{len(result.unattached)} lignes non rattachées, {flagged} dossiers avec au moins un constat."
    )

    comparison = None
    if args.scenarios:
        comparison = compare_with_scenarios(result, rows, args.scenarios)
        print(
            f"Lignes rattachées au bon dossier : {comparison.correctly_attached}/{comparison.export_rows}, "
            f"au mauvais : {len(comparison.wrongly_attached)}, non rattachées : {len(comparison.not_attached)}."
        )
        print(f"Noms inversés rattachés : {comparison.swapped_attached}/{comparison.swapped_expected}.")
        for code, expected in comparison.findings_expected.items():
            print(f"{code} : {comparison.findings_found[code]}/{expected} retrouvés.")
        print(f"Constats manqués : {len(comparison.missed)}, constats en trop : {len(comparison.false_alerts)}.")
        for line in comparison.wrongly_attached + comparison.not_attached:
            print(f"  rattachement : {line}")
        for line in comparison.missed:
            print(f"  manqué : {line}")
        for line in comparison.false_alerts:
            print(f"  en trop : {line}")

    if args.out:
        export = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "code_version": __version__,
            "git_commit": git_commit(),
            "dossiers": str(args.dossiers),
            "export": str(args.export),
            "config": config.model_dump(mode="json"),
            "comparison": comparison.model_dump() if comparison else None,
            "result": result.model_dump(mode="json"),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Résultats écrits dans {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
