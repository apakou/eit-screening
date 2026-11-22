"""Modèle de données d'un dossier de candidature.

Le même modèle sert dans les deux sens : le module d'import le produit à
partir d'un export PDF SurveyMonkey Apply, et le générateur de dossiers
fictifs le prend en entrée pour fabriquer un PDF au même format.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

UploadKind = Literal[
    "personal_statement_video", "reflection_video", "resume", "evidence", "other"
]


class UploadedFile(BaseModel):
    """Fichier envoyé par le candidat (le fichier lui-même n'est pas dans le PDF)."""

    kind: UploadKind = "other"
    label: str
    link_text: str
    filename: str
    size_bytes: int
    url: str | None = None


class FormItem(BaseModel):
    """Question et réponse brutes, telles qu'elles apparaissent dans l'export.

    Cette liste conserve tout le formulaire, y compris les questions que le
    module ne sait pas encore ranger dans un champ : rien n'est perdu si MEST
    modifie son formulaire d'une cohorte à l'autre.
    """

    task: str
    section: str | None = None
    question: str
    help_text: str | None = None
    answer: str | None = None
    file: UploadedFile | None = None


class TaskStatus(BaseModel):
    """Étape de la candidature (éligibilité, formulaire, test, vidéo de réflexion)."""

    title: str
    status: str | None = None
    completed_on: date | None = None


class EligibilityAnswer(BaseModel):
    key: str | None = None
    question: str
    answer: bool | None = None


class Personal(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    based_in: str | None = None
    country_of_residence: str | None = None
    country_of_citizenship: str | None = None
    dual_citizenship: bool | None = None
    interview_city: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    heard_about: str | None = None
    referral_source: str | None = None
    referrer_name: str | None = None
    referrer_email: str | None = None
    referrer_phone: str | None = None
    applied_before: bool | None = None
    participated_before: bool | None = None


class Education(BaseModel):
    degree: str | None = None
    major: str | None = None
    institution: str | None = None
    institution_other: str | None = None
    location: str | None = None
    graduation_date: date | None = None
    other_training: str | None = None


class WorkExperience(BaseModel):
    organisation: str | None = None
    job_title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    current: bool | None = None
    duration_months: int | None = None


class Essay(BaseModel):
    question: str
    answer: str | None = None
    word_count: int = 0


class Reference(BaseModel):
    kind: Literal["professional", "academic"]
    full_name: str | None = None
    title: str | None = None
    relationship: str | None = None
    phone: str | None = None
    email: str | None = None


class AttachmentPage(BaseModel):
    """Page ajoutée après le formulaire (CV, certificats)."""

    page_number: int
    text: str = ""
    needs_ocr: bool = False
    image_count: int = 0


class Application(BaseModel):
    application_id: str
    applicant_display_name: str | None = None
    applicant_email: str | None = None
    program: str | None = None
    last_submitted: datetime | None = None
    labels: list[str] = Field(default_factory=list)

    tasks: list[TaskStatus] = Field(default_factory=list)
    eligibility: list[EligibilityAnswer] = Field(default_factory=list)
    personal: Personal = Field(default_factory=Personal)
    education: list[Education] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    essays: list[Essay] = Field(default_factory=list)
    uploads: list[UploadedFile] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)

    form_page_count: int = 0
    attachment_pages: list[AttachmentPage] = Field(default_factory=list)
    items: list[FormItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def eligibility_value(self, key: str) -> bool | None:
        """Réponse à une question d'éligibilité, repérée par sa clé."""
        for answer in self.eligibility:
            if answer.key == key:
                return answer.answer
        return None

    def upload(self, kind: UploadKind) -> UploadedFile | None:
        """Premier fichier envoyé d'un type donné, s'il existe."""
        for item in self.uploads:
            if item.kind == kind:
                return item
        return None
