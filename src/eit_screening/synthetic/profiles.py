"""Fabrication de candidats fictifs, avec des anomalies placées volontairement.

Chaque dossier suit un *scénario* : un niveau de qualité et, pour une partie
des dossiers, une anomalie connue d'avance (test introuvable, nom inversé,
réponses génériques, âge hors tranche…). Comme l'anomalie est posée à la
construction, on sait exactement ce que le système doit retrouver.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import quote

from ..models import (
    Application,
    Education,
    EligibilityAnswer,
    Essay,
    Personal,
    Reference,
    TaskStatus,
    UploadedFile,
    WorkExperience,
)
from . import content as C
from . import form_text as F

# Paramètres de la cohorte fictive, calqués sur le guide d'évaluation de la
# promotion 2027 (âge 21-35 au 1er janvier 2027, Afrique de l'Ouest ou de l'Est,
# test ClassMarker à rendre le 20 juillet 23 h 59 GMT, plateforme ouverte
# jusqu'au 22). L'année 2026 du test est une hypothèse.
AGE_REFERENCE = date(2027, 1, 1)
AGE_MIN, AGE_MAX = 21, 35
ASSESSMENT_DEADLINE = date(2026, 7, 20)  # jour compris, jusqu'à 23 h 59 GMT
PLATFORM_CLOSE = date(2026, 7, 22)
ASSESSMENT_MINUTES = 70  # hypothèse : durée du test ClassMarker non donnée par le guide
ASSESSMENT_TOTAL_POINTS = 50  # relevé sur une fiche de résultat ClassMarker 2027
ID_PREFIX = "EIT-2027-"
UPLOAD_BASE_URL = "https://apply.example.org/protected"

TIERS = ("fort", "moyen", "faible")

ANOMALIES: dict[str, str] = {
    "assessment_name_swapped": "Nom et prénom inversés dans l'export du test, avec une autre adresse e-mail",
    "assessment_not_found": "Aucun résultat de test pour ce candidat",
    "assessment_late": "Test passé après la date limite",
    "assessment_too_fast": "Test terminé en un temps anormalement court avec un score élevé",
    "generic_ai_answers": "Réponses libres génériques, sans aucun fait personnel",
    "age_out_of_range": "Date de naissance hors de la tranche d'âge, malgré la réponse « Yes »",
    "age_borderline": "20 ans au dépôt et 21 ans au 1er janvier 2027, ou 35 ans au 1er janvier 2027",
    "citizenship_outside_region": "Nationalité hors Afrique de l'Ouest et de l'Est, malgré la réponse « Yes »",
    "graduation_after_cutoff": "Diplôme obtenu en 2028 : écarté par le guide",
    "graduation_review": "Diplôme obtenu en 2027 : mois à examiner",
    "missing_resume": "CV non fourni",
    "poor_audio": "Vidéo de présentation presque inaudible",
}
# Composition de la cohorte de 40 (16 anomalies) : chaque anomalie une fois, et
# quatre une seconde fois (voir docs/feuille-de-route.md).
_ANOMALY_SEQUENCE = list(ANOMALIES) + [
    "assessment_name_swapped",
    "assessment_late",
    "assessment_too_fast",
    "age_out_of_range",
]


@dataclass
class Scenario:
    tier: str
    anomalies: list[str] = field(default_factory=list)

    def has(self, code: str) -> bool:
        return code in self.anomalies

    @property
    def expected_eligible(self) -> bool:
        return not (
            self.has("age_out_of_range") or self.has("citizenship_outside_region") or self.has("graduation_after_cutoff")
        )


@dataclass
class Certificate:
    title: str
    subject: str
    issued: str
    as_image: bool


@dataclass
class Resume:
    headline: str
    skills: str
    languages: list[str]
    bullets: list[list[str]]  # une liste de puces par expérience


@dataclass
class Dossier:
    application: Application
    scenario: Scenario
    resume: Resume | None
    certificates: list[Certificate]
    personal_statement: str
    reflection: str
    assessment: dict | None


class _Picker:
    """Tire les textes à tour de rôle pour limiter les répétitions dans une cohorte."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._queues: dict[str, list] = {}

    def take(self, key: str, pool: list):
        queue = self._queues.get(key)
        if not queue:
            queue = list(pool)
            self._rng.shuffle(queue)
            self._queues[key] = queue
        return queue.pop()


def plan_scenarios(count: int, rng: random.Random, anomaly_share: float = 0.4) -> list[Scenario]:
    """Répartit les dossiers : cas réguliers et cas porteurs d'une anomalie."""
    anomaly_count = round(count * anomaly_share)
    scenarios: list[Scenario] = []
    for index in range(anomaly_count):
        code = _ANOMALY_SEQUENCE[index % len(_ANOMALY_SEQUENCE)]
        if code == "generic_ai_answers":
            tier = "moyen"
        elif code == "assessment_too_fast":
            tier = "faible"
        else:
            tier = rng.choices(TIERS, weights=(3, 4, 2))[0]
        scenarios.append(Scenario(tier=tier, anomalies=[code]))
    for _ in range(count - anomaly_count):
        scenarios.append(Scenario(tier=rng.choices(TIERS, weights=(35, 45, 20))[0]))
    rng.shuffle(scenarios)
    return scenarios


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _phone(code: str, rng: random.Random) -> str:
    # Numéros volontairement invalides (préfixe 000).
    return f"{code}000{rng.randrange(10**6):06d}"


def _random_date(start: date, end: date, rng: random.Random) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def _size(low: float, high: float, unit: int, rng: random.Random) -> int:
    """Taille de fichier qui s'affiche avec une décimale, comme dans l'export."""
    return int(round(round(rng.uniform(low, high), 1) * unit))


def _upload_url(rng: random.Random, name: str) -> str:
    return f"{UPLOAD_BASE_URL}/rg/{rng.randrange(10**6, 10**7)}/{rng.randrange(10**7, 10**8)}/{quote(name)}"


def _person(rng: random.Random, group: str, gender: str | None = None) -> tuple[str, str]:
    names = C.NAME_GROUPS[group]
    gender = gender or rng.choice(["Male", "Female"])
    return rng.choice(names[gender]), rng.choice(names["last"])


# --------------------------------------------------------------------------
# Construction d'un dossier
# --------------------------------------------------------------------------


def build_dossier(number: int, scenario: Scenario, rng: random.Random, picker: _Picker) -> Dossier:
    tier = scenario.tier
    voice = "generique" if scenario.has("generic_ai_answers") else tier
    application_id = f"{ID_PREFIX}{number:06d}"

    # --- Identité -----------------------------------------------------------
    gender = rng.choices(["Male", "Female"], weights=(55, 45))[0]
    countries = list(C.COUNTRIES)
    country = rng.choices(countries, weights=[C.COUNTRY_WEIGHTS.get(c, 1) for c in countries])[0]
    citizenship = country
    name_group = C.COUNTRY_NAME_GROUP[country]
    if scenario.has("citizenship_outside_region"):
        country, citizenship = "Ghana", rng.choice(list(C.OUTSIDE_REGION))
        name_group = "hors_zone"
    first_name, last_name = _person(rng, name_group, gender)
    local_group = C.COUNTRY_NAME_GROUP[country]
    code, city, language, institutions = C.COUNTRIES[country]
    based_in = country if country in C.BASED_IN_OPTIONS else "Other"
    if based_in != "Other":
        interview_city = C.BASED_IN_OPTIONS[country]
    elif country in ("Mali", "Guinea", "The Gambia"):
        interview_city = "Dakar"
    elif country == "Niger":
        interview_city = "Lagos"
    else:
        interview_city = "Accra"

    # Dossiers réguliers : 22 à 34 ans, loin des bornes signalées par le guide.
    age = rng.choice([22, 23, 24, 24, 25, 25, 26, 26, 27, 28, 29, 30, 31, 32, 33, 34])
    if scenario.has("age_out_of_range"):
        age = rng.choice([19, 20, 36, 37])
    # Né après le 1er janvier : l'âge à la date de référence vaut exactement ``age``.
    birth_year = AGE_REFERENCE.year - 1 - age
    date_of_birth = date(birth_year, 1, 2) + timedelta(days=rng.randrange(360))
    if scenario.has("age_borderline"):
        if rng.random() < 0.5:
            # 21 ans au 1er janvier 2027, mais 20 ans au dépôt (juin-juillet 2026).
            date_of_birth = date(AGE_REFERENCE.year - 1 - AGE_MIN, 8, 1) + timedelta(days=rng.randrange(150))
        else:
            # 35 ans au 1er janvier 2027 : atteindra 36 ans pendant le programme.
            date_of_birth = date(AGE_REFERENCE.year - 1 - AGE_MAX, 1, 2) + timedelta(days=rng.randrange(360))

    handle = f"{_slug(first_name)}.{_slug(last_name)}{rng.randrange(10, 99)}"
    email = f"{handle}@{rng.choice(C.EMAIL_DOMAINS)}"
    referral = rng.random() < 0.3
    personal = Personal(
        first_name=first_name,
        last_name=last_name,
        based_in=based_in,
        country_of_residence=country,
        country_of_citizenship=citizenship,
        dual_citizenship=False,
        interview_city=interview_city,
        gender=gender,
        date_of_birth=date_of_birth,
        email=email,
        phone=_phone(C.OUTSIDE_REGION.get(citizenship, code), rng),
        linkedin_url=f"https://www.linkedin.com/in/{handle.replace('.', '-')}-example",
        heard_about="Referral" if referral else rng.choice(C.HEARD_ABOUT),
        applied_before=rng.random() < 0.1,
        participated_before=False,
    )
    if referral:
        referrer_first, referrer_last = _person(rng, local_group)
        personal.referral_source = rng.choice(["MEST alumni", "Friend", "Other"])
        personal.referrer_name = f"{referrer_first} {referrer_last}"
        personal.referrer_email = f"{_slug(referrer_first)}.{_slug(referrer_last)}@example.org"
        personal.referrer_phone = _phone(code, rng)

    # --- Formation ----------------------------------------------------------
    technical = rng.random() < {"fort": 0.9, "moyen": 0.75, "faible": 0.4}[tier]
    major = rng.choice(C.MAJORS_TECH if technical else C.MAJORS_OTHER)
    institution_name = rng.choice(institutions)
    listed = institution_name in C.LISTED_INSTITUTIONS
    training = None
    if rng.random() < {"fort": 0.8, "moyen": 0.5, "faible": 0.15}[tier]:
        training = rng.choice(C.TRAININGS)
    graduation = _random_date(date(2020, 6, 1), date(2026, 6, 30), rng)
    if scenario.has("graduation_review"):
        graduation = _random_date(date(2027, 1, 1), date(2027, 12, 31), rng)
    elif scenario.has("graduation_after_cutoff"):
        graduation = _random_date(date(2028, 1, 1), date(2028, 12, 31), rng)
    education = Education(
        degree=rng.choice(C.DEGREES),
        major=major,
        institution=institution_name if listed else "Other",
        institution_other=None if listed else institution_name,
        location=country,
        graduation_date=graduation,
        other_training=training,
    )

    # --- Expériences ----------------------------------------------------------
    experience_count = {"fort": 2, "moyen": rng.choice([1, 2]), "faible": 1}[tier]
    organisations = rng.sample(C.ORGANISATIONS, experience_count)
    experiences: list[WorkExperience] = []
    current = rng.random() < 0.6
    start = _random_date(date(2023, 1, 1), date(2026, 4, 30), rng)
    first = WorkExperience(
        organisation=organisations[0],
        job_title=rng.choice(C.JOB_TITLES[tier]),
        start_date=start,
        location=country,
        current=current,
    )
    if not current:
        months = rng.randint(3, 14)
        first.end_date = min(start + timedelta(days=30 * months), date(2026, 5, 31))
        first.duration_months = max(1, round((first.end_date - start).days / 30))
    experiences.append(first)
    if experience_count == 2:
        months = rng.randint(3, 18)
        previous_start = _random_date(date(2021, 1, 1), date(2022, 6, 30), rng)
        experiences.append(
            WorkExperience(
                organisation=organisations[1],
                job_title=rng.choice(C.JOB_TITLES["moyen" if tier == "fort" else tier]),
                location=country,
                start_date=previous_start,
                end_date=previous_start + timedelta(days=30 * months),
                duration_months=months,
            )
        )

    # --- Réponses libres ------------------------------------------------------
    idea = picker.take("idea", C.IDEAS)
    slots = {
        "city": city,
        "country": country,
        "language": language,
        "year": str(rng.randint(2021, 2024)),
        "training": training or rng.choice(C.TRAININGS),
        "first_name": first_name,
        "major": major,
        "institution": institution_name,
        "a_job_title": ("an " if first.job_title[0] in "AEIOU" else "a ") + first.job_title,
        "organisation": first.organisation,
        "skills": rng.choice(C.SKILLS[tier]),
    }
    slots.update({key: value.format(**slots) for key, value in idea.items()})
    essays: list[Essay] = []
    for index, (question, pool) in enumerate(zip(F.ESSAY_QUESTIONS, C.ESSAY_POOLS)):
        answer = picker.take(f"essay{index}:{voice}", pool[voice]).format(**slots)
        essays.append(Essay(question=question, answer=answer, word_count=len(answer.split())))

    # --- Transcriptions des vidéos --------------------------------------------
    slots["reason"] = picker.take("reason", C.STATEMENT_REASON).format(**slots)
    slots["moment"] = picker.take("moment", C.STATEMENT_MOMENT)
    slots["gain"] = picker.take("gain", C.STATEMENT_GAIN)
    statement_voice = "inaudible" if scenario.has("poor_audio") else voice
    personal_statement = picker.take(
        f"statement:{statement_voice}", C.STATEMENT[statement_voice]
    ).format(**slots)
    reflection_voice = "rapide" if scenario.has("assessment_too_fast") else tier
    reflection = picker.take(f"reflection:{reflection_voice}", C.REFLECTION[reflection_voice])

    # --- Calendrier de la candidature -----------------------------------------
    screening_day = _random_date(date(2026, 6, 10), date(2026, 7, 5), rng)
    form_day = screening_day + timedelta(days=rng.randint(2, 12))
    assessment_day = min(form_day + timedelta(days=rng.randint(1, 8)), ASSESSMENT_DEADLINE)
    if scenario.has("assessment_late"):
        # Après la date limite, mais avant la fermeture de la plateforme (21 ou 22 juillet).
        assessment_day = ASSESSMENT_DEADLINE + timedelta(days=rng.randint(1, (PLATFORM_CLOSE - ASSESSMENT_DEADLINE).days))
    submitted = datetime(
        assessment_day.year, assessment_day.month, assessment_day.day,
        rng.randint(7, 23), rng.randint(0, 59),
    )
    tasks = [
        TaskStatus(title=F.TASK_ELIGIBILITY, status="Completed", completed_on=screening_day),
        TaskStatus(title=F.PROGRAM, status="Completed", completed_on=form_day),
        TaskStatus(title=F.TASK_ASSESSMENT, status="Completed", completed_on=assessment_day),
        TaskStatus(title=F.TASK_REFLECTION, status="Completed", completed_on=assessment_day),
    ]

    # --- Fichiers envoyés -------------------------------------------------------
    uploads: list[UploadedFile] = []
    stamp = f"{form_day:%Y%m%d}_{rng.randrange(10**6):06d}"
    video_name = f"VID_{stamp}.mp4"
    uploads.append(
        UploadedFile(
            kind="personal_statement_video",
            label=F.VIDEO_PROMPT[0],
            link_text=video_name,
            filename=f"{video_name}.mp4",
            size_bytes=_size(35, 600, 1_000_000, rng),
            url=_upload_url(rng, video_name),
        )
    )
    resume: Resume | None = None
    if not scenario.has("missing_resume"):
        resume_name = rng.choice(["Resume.pdf", "CV.pdf", f"{first_name}_{last_name}_CV.pdf"])
        uploads.append(
            UploadedFile(
                kind="resume",
                label=F.RESUME_PROMPT,
                link_text=resume_name,
                filename=f"{resume_name}.pdf",
                size_bytes=_size(40, 400, 1_000, rng),
                url=_upload_url(rng, resume_name),
            )
        )
        resume = Resume(
            headline=rng.choice(C.RESUME_HEADLINES[tier]),
            skills=slots["skills"],
            languages=["English", "French"] if country not in ("Ghana", "Nigeria") else ["English"],
            bullets=[
                rng.sample(C.RESUME_BULLETS[tier], k=min(2, len(C.RESUME_BULLETS[tier])))
                for _ in experiences
            ],
        )
    certificates: list[Certificate] = []
    evidence_count = {"fort": rng.choice([2, 3]), "moyen": rng.choice([1, 2]), "faible": rng.choice([0, 1])}[tier]
    for index in range(evidence_count):
        title, subject = C.CERTIFICATE_TITLES[(number + index) % len(C.CERTIFICATE_TITLES)]
        subject = subject.format(**slots)
        evidence_name = rng.choice(
            [f"{first_name} {last_name}.pdf", f"certificate_{index + 1}.pdf", f"{_slug(subject)}.pdf"]
        )
        uploads.append(
            UploadedFile(
                kind="evidence",
                label=f"Evidence {index + 1}",
                link_text=evidence_name,
                filename=f"{evidence_name}.pdf",
                size_bytes=_size(80, 900, 1_000, rng),
                url=_upload_url(rng, evidence_name),
            )
        )
        certificates.append(
            Certificate(title=title, subject=subject, issued=slots["year"], as_image=index % 2 == 0)
        )
    reflection_name = f"REFLECT_{assessment_day:%Y%m%d}_{rng.randrange(10**6):06d}"
    uploads.append(
        UploadedFile(
            kind="reflection_video",
            label=F.TASK_REFLECTION,
            link_text=reflection_name,
            filename=f"{reflection_name}.mp4",
            size_bytes=_size(20, 200, 1_000_000, rng),
            url=f"{UPLOAD_BASE_URL}/tr/{rng.randrange(10**6, 10**7)}/{rng.randrange(10**5, 10**6)}/{reflection_name}.mp4",
        )
    )
    url_count = {"fort": rng.choice([1, 2]), "moyen": rng.choice([0, 1]), "faible": 0}[tier]
    evidence_urls = [
        f"https://portfolio.example.org/{handle.replace('.', '-')}",
        f"https://code.example.org/{handle.replace('.', '-')}/project",
    ][:url_count]

    # --- Références -------------------------------------------------------------
    references: list[Reference] = []
    for kind, title, relationship in (
        ("professional", f"Manager at {first.organisation}", "Supervisor"),
        ("academic", f"Lecturer at {institution_name}", "Lecturer"),
    ):
        reference_first, reference_last = _person(rng, local_group)
        references.append(
            Reference(
                kind=kind,
                full_name=f"{reference_first} {reference_last}",
                title=title,
                relationship=relationship,
                phone=_phone(code, rng),
                email=f"{_slug(reference_first)}.{_slug(reference_last)}@example.org",
            )
        )

    application = Application(
        application_id=application_id,
        applicant_display_name=f"{first_name} {last_name.upper()}",
        applicant_email=email,
        program=F.PROGRAM,
        last_submitted=submitted,
        labels=[gender, based_in],
        tasks=tasks,
        eligibility=[
            EligibilityAnswer(key=key, question=question, answer=True)
            for key, question, _ in F.ELIGIBILITY_QUESTIONS
        ],
        personal=personal,
        education=[education],
        experience=experiences,
        essays=essays,
        uploads=uploads,
        evidence_urls=evidence_urls,
        references=references,
    )

    return Dossier(
        application=application,
        scenario=scenario,
        resume=resume,
        certificates=certificates,
        personal_statement=personal_statement,
        reflection=reflection,
        assessment=_assessment_row(application, scenario, assessment_day, rng),
    )


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _classmarker_date(moment: datetime) -> str:
    """Écrit « Tue 21 Jul '26 5:14pm », format des fiches de résultat ClassMarker."""
    hour = moment.hour % 12 or 12
    meridiem = "am" if moment.hour < 12 else "pm"
    return (
        f"{_WEEKDAYS[moment.weekday()]} {moment.day} {_MONTHS[moment.month - 1]} "
        f"'{moment:%y} {hour}:{moment:%M}{meridiem}"
    )


def _assessment_row(
    application: Application, scenario: Scenario, day: date, rng: random.Random
) -> dict | None:
    """Ligne du candidat dans l'export de la plateforme de test.

    Les valeurs suivent les formats relevés sur une fiche ClassMarker 2027 :
    points sur 50, durée « hh:mm:ss », date « Tue 21 Jul '26 5:14pm ». Les noms
    de colonnes, eux, restent une supposition (voir ``assessment.toml``).
    """
    if scenario.has("assessment_not_found"):
        return None
    low, high = {"fort": (68, 95), "moyen": (48, 78), "faible": (22, 55)}[scenario.tier]
    score = rng.randint(low, high)
    minutes = rng.randint(38, ASSESSMENT_MINUTES)
    if scenario.has("assessment_too_fast"):
        score, minutes = rng.randint(86, 98), rng.randint(7, 13)
    person = application.personal
    first_name, last_name, email = person.first_name, person.last_name, person.email
    if scenario.has("assessment_name_swapped"):
        first_name, last_name = last_name, first_name
        email = f"{_slug(person.last_name)}{_slug(person.first_name)[0]}{rng.randrange(100, 999)}@example.net"
    elif rng.random() < 0.25:
        # Variation de saisie banale : nom en capitales.
        last_name = last_name.upper()
    points = round(score * ASSESSMENT_TOTAL_POINTS / 100)
    percent = round(points / ASSESSMENT_TOTAL_POINTS * 100, 1)
    # Secondes déduites des valeurs déjà tirées, et non d'un tirage de plus :
    # consommer le générateur aléatoire ici décalerait toute la cohorte.
    seconds = (minutes * 7 + points) % 60
    completed = datetime(day.year, day.month, day.day, rng.randint(7, 22), rng.randint(0, 59))
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "score_points": points,
        "score_max": ASSESSMENT_TOTAL_POINTS,
        "score_percent": f"{percent:g}%",
        "duration": f"{minutes // 60:02d}:{minutes % 60:02d}:{seconds:02d}",
        "completed_at": _classmarker_date(completed),
        # Valeurs commodes pour scenarios.csv et les tests. Ce ne sont pas des
        # colonnes de l'export : l'écriture du CSV les ignore.
        "time_taken_minutes": round(minutes + seconds / 60, 2),
        "completed_at_iso": completed.isoformat(timespec="minutes"),
    }


def build_cohort(count: int, seed: int, first_number: int = 1001) -> list[Dossier]:
    """Fabrique une cohorte reproductible : même graine, mêmes dossiers."""
    rng = random.Random(seed)
    picker = _Picker(rng)
    scenarios = plan_scenarios(count, rng)
    return [
        build_dossier(first_number + index, scenario, rng, picker)
        for index, scenario in enumerate(scenarios)
    ]
