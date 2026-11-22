"""Rendu d'un dossier fictif en PDF, au format de l'export SurveyMonkey Apply.

Le PDF reprend la grammaire visuelle de l'export réel : libellés gris,
réponses dans un rectangle gris, traits fins entre les questions, liens bleus
suivis de « Filename: … Size: … », pied de page « n / N », puis les pièces
jointes (CV en texte, certificats en texte ou en image). Le module d'import
lit donc un dossier fictif exactement comme un dossier réel.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..ingestion.smapply_pdf import NO_RESPONSE
from ..models import Application, WorkExperience
from . import form_text as F
from .profiles import Certificate, Dossier

PAGE_W, PAGE_H = 612.0, 792.0
LEFT, RIGHT = 36.0, 576.0
TOP, BOTTOM = 33.0, 742.0

FONT, BOLD = "Helvetica", "Helvetica-Bold"
GREY_TEXT = (0.2, 0.2431, 0.2824)
BLACK = (0.0, 0.0, 0.0)
BLUE = (0.0, 0.0, 0.9333)
BOX_FILL = (0.9333, 0.9333, 0.9333)
RULE_FILL = (0.9608, 0.9608, 0.9608)


def _fmt_date(value: date | None) -> str | None:
    return None if value is None else f"{value:%b} {value.day} {value.year}"


def _fmt_datetime(value: datetime) -> str:
    hour = value.hour % 12 or 12
    return f"{value:%b} {value.day} {value.year} {hour}:{value:%M} {value:%p} (GMT)"


def _fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    return f"{size_bytes / 1_000:.1f} kB"


def _yes_no(value: bool | None) -> str | None:
    return None if value is None else ("Yes" if value else "No")


class _Form:
    """Mise en page en flux : on empile des blocs, avec saut de page au besoin."""

    def __init__(self) -> None:
        self.pages: list[list[tuple]] = [[]]
        self.y = TOP

    # -- primitives -----------------------------------------------------------

    def _text(self, x, top, text, font=FONT, size=10.0, rgb=GREY_TEXT) -> None:
        self.pages[-1].append(("text", x, top, text, font, size, rgb))

    def _rich(self, x, top, parts, size=10.0, rgb=BLACK) -> None:
        """Une ligne mêlant gras et maigre, comme « ID: 0000001001 »."""
        for text, font in parts:
            self._text(x, top, text, font, size, rgb)
            x += stringWidth(text, font, size)

    def _rect(self, x0, top, x1, bottom, rgb) -> None:
        self.pages[-1].append(("rect", x0, top, x1, bottom, rgb))

    def _room(self, height: float) -> None:
        if self.y + height > BOTTOM and self.pages[-1]:
            self.pages.append([])
            self.y = TOP

    @staticmethod
    def _lines(paragraphs, pitch=20.0, gap=33.0, size=10.0, width=RIGHT - LEFT):
        """Découpe des paragraphes en lignes, avec leur décalage vertical."""
        lines, offset = [], 0.0
        for text, font in paragraphs:
            for index, line in enumerate(simpleSplit(text, font, size, width) or [""]):
                if lines:
                    offset += gap if index == 0 else pitch
                lines.append((offset, line, font))
        return lines

    def _rule(self, top: float) -> None:
        self._rect(LEFT, top, RIGHT, top + 1.0, RULE_FILL)

    # -- blocs ----------------------------------------------------------------

    def header(self, app: Application) -> None:
        self._text(LEFT, 43.2, f"Application: {app.application_id}", BOLD, 20.0, BLACK)
        self._text(LEFT, 79.0, f"{app.applicant_display_name} - {app.applicant_email}", rgb=BLACK)
        self._text(LEFT, 90.0, app.program, rgb=BLACK)
        self._text(LEFT, 114.0, "Summary", BOLD, rgb=BLACK)
        self._rich(LEFT, 137.9, [("ID: ", BOLD), (app.application_id, FONT)])
        self._rich(LEFT, 148.9, [("Last submitted: ", BOLD), (_fmt_datetime(app.last_submitted), FONT)])
        self._rich(LEFT, 159.9, [("Labels: ", BOLD), (", ".join(app.labels), FONT)])
        self.y = 184.9

    def task(
        self,
        title: str,
        status: str,
        completed_on: date | None,
        form_title: str | None = None,
        gap: float = 20.0,
        room: float = 200.0,
    ) -> None:
        """Titre d'une étape, avec son état et sa date.

        ``room`` est la hauteur à garder sous le titre, pour qu'il ne reste pas
        seul en bas de page.
        """
        self._room(room)
        if self.y > TOP + 1:
            self.y += gap
        self._text(LEFT, self.y, title, BOLD, 15.0, BLACK)
        self._text(LEFT, self.y + 29.2, f"{status} - {_fmt_date(completed_on)}", BOLD, 8.3, BLACK)
        if form_title:
            self._text(LEFT, self.y + 48.5, form_title, BOLD, 18.0, BLACK)
            self.y += 95.7
        else:
            self.y += 49.0

    def question(self, label, answer, help_text=None, rule=True, intro=()) -> None:
        """Libellé (et aide éventuelle), réponse dans un rectangle gris, trait fin."""
        paragraphs = [(text, FONT) for text in intro] + [(label, FONT)]
        if help_text:
            paragraphs.append((help_text, FONT))
        label_lines = self._lines(paragraphs, gap=35.0 if intro else 33.0)
        answer_text = answer if answer not in (None, "") else NO_RESPONSE
        answer_lines = self._lines(
            [(text, FONT) for text in answer_text.split("\n")], gap=40.0, width=RIGHT - LEFT - 10
        )
        box_height = answer_lines[-1][0] + 30.0
        self._room(label_lines[-1][0] + 23 + box_height + 32)
        for offset, line, font in label_lines:
            self._text(LEFT, self.y + offset, line, font)
        box_top = self.y + label_lines[-1][0] + 23.0
        self._rect(LEFT, box_top, RIGHT, box_top + box_height, BOX_FILL)
        for offset, line, font in answer_lines:
            self._text(LEFT + 5, box_top + 10.0 + offset, line, font)
        self.y = box_top + box_height
        if rule:
            self._rule(self.y + 30.0)
            self.y += 46.0
        else:
            self.y += 9.0

    def section(self, title: str, intro: str | None = None, before: str | None = None) -> None:
        """En-tête de section, fermé par un trait fin."""
        paragraphs = [(text, FONT) for text in (before, title, intro) if text]
        lines = self._lines(paragraphs, gap=28.0 if before else 33.0)
        self._room(lines[-1][0] + 47 + 110)
        for offset, line, font in lines:
            self._text(LEFT, self.y + offset, line, font)
        self._rule(self.y + lines[-1][0] + 26.0)
        self.y += lines[-1][0] + 46.0

    def upload(self, paragraphs, link_text, filename, size_bytes, url, rule=True, task_style=False) -> None:
        """Fichier envoyé : lien bleu, puis ligne « Filename: … Size: … »."""
        lines = self._lines(paragraphs, pitch=11.0 if task_style else 20.0, gap=21.0 if task_style else 30.0)
        rgb = BLACK if task_style else GREY_TEXT
        self._room(lines[-1][0] + 26 + 31 + 26)
        for offset, line, font in lines:
            self._text(LEFT, self.y + offset, line, font, rgb=rgb)
        link_font, link_size = (BOLD, 11.7) if task_style else (FONT, 10.0)
        link_top = self.y + lines[-1][0] + (23.6 if task_style else 26.0)
        width = stringWidth(link_text, link_font, link_size)
        self._text(LEFT, link_top, link_text, link_font, link_size, BLUE)
        self._rect(LEFT, link_top + link_size * 0.9, LEFT + width, link_top + link_size * 0.9 + 1.0, BLUE)
        self.pages[-1].append(("link", LEFT, link_top - 1.0, LEFT + width, link_top + link_size, url))
        meta_top = link_top + (24.6 if task_style else 31.0)
        self._rich(
            LEFT,
            meta_top,
            [("Filename: ", BOLD), (f"{filename} ", FONT), ("Size: ", BOLD), (_fmt_size(size_bytes), FONT)],
            size=8.3 if task_style else 10.0,
        )
        self.y = meta_top + 25.0
        if rule:
            self._rule(self.y)
            self.y += 16.0

    def black_paragraphs(self, paragraphs: list[str]) -> None:
        """Texte d'instructions en noir (étapes du test et de la vidéo de réflexion)."""
        for text in paragraphs:
            lines = self._lines([(text, FONT)], pitch=11.0)
            self._room(lines[-1][0] + 21)
            for offset, line, font in lines:
                self._text(LEFT, self.y + offset, line, font, rgb=BLACK)
            self.y += lines[-1][0] + 21.0

    # -- écriture ---------------------------------------------------------------

    def draw(self, pdf: canvas.Canvas) -> int:
        total = len(self.pages)
        for number, operations in enumerate(self.pages, 1):
            pdf.setPageSize((PAGE_W, PAGE_H))
            for operation in operations:
                kind = operation[0]
                if kind == "text":
                    _, x, top, text, font, size, rgb = operation
                    pdf.setFillColorRGB(*rgb)
                    pdf.setFont(font, size)
                    pdf.drawString(x, PAGE_H - top - 0.793 * size, text)
                elif kind == "rect":
                    _, x0, top, x1, bottom, rgb = operation
                    pdf.setFillColorRGB(*rgb)
                    pdf.rect(x0, PAGE_H - bottom, x1 - x0, bottom - top, stroke=0, fill=1)
                elif kind == "link":
                    _, x0, top, x1, bottom, url = operation
                    pdf.linkURL(url, (x0, PAGE_H - bottom, x1, PAGE_H - top), relative=0, thickness=0)
            footer = f"{number} / {total}"
            pdf.setFillColorRGB(*BLACK)
            pdf.setFont(FONT, 10.0)
            pdf.drawString((PAGE_W - stringWidth(footer, FONT, 10.0)) / 2, PAGE_H - 767.1 - 7.93, footer)
            pdf.showPage()
        return total


# --------------------------------------------------------------------------
# Formulaire
# --------------------------------------------------------------------------


def _experience_block(form: _Form, experience: WorkExperience, first: bool, more: bool) -> None:
    form.question("Organisation name", experience.organisation)
    form.question("Job title", experience.job_title)
    if first:
        # Même ordre que dans l'export réel pour l'expérience la plus récente.
        form.question("Start date", _fmt_date(experience.start_date))
        form.question("Location", experience.location)
        form.question("Do you still work here?", _yes_no(experience.current))
        if experience.current is False:
            form.question("End date", _fmt_date(experience.end_date))
            form.question("Total duration (in months)", str(experience.duration_months))
        form.question("Add another experience?", _yes_no(more), rule=more)
    else:
        form.question("Location", experience.location)
        form.question("Start date", _fmt_date(experience.start_date))
        form.question("End date", _fmt_date(experience.end_date))
        form.question("Total duration (in months)", str(experience.duration_months), rule=False)


def _build_form(app: Application) -> _Form:
    form = _Form()
    person = app.personal
    tasks = {task.title: task for task in app.tasks}
    uploads = {kind: app.upload(kind) for kind in ("personal_statement_video", "resume", "reflection_video")}
    evidence = [item for item in app.uploads if item.kind == "evidence"]

    # --- Éligibilité --------------------------------------------------------
    form.header(app)
    screening = tasks[F.TASK_ELIGIBILITY]
    form.task(
        screening.title, screening.status, screening.completed_on,
        form_title=F.TASK_ELIGIBILITY, gap=0.0,
    )
    form.question("First Name", person.first_name, intro=F.ELIGIBILITY_INTRO)
    form.question("Last Name", person.last_name)
    answers = {answer.key: answer.answer for answer in app.eligibility}
    for index, (key, question, help_text) in enumerate(F.ELIGIBILITY_QUESTIONS):
        last = index == len(F.ELIGIBILITY_QUESTIONS) - 1
        form.question(question, _yes_no(answers.get(key)), help_text, rule=not last)

    # --- Formulaire de candidature ------------------------------------------
    main = tasks[F.PROGRAM]
    form.task(main.title, main.status, main.completed_on, form_title=F.FORM_TITLE)
    # « Personal Information » suit directement le texte d'introduction du formulaire.
    form.section(*F.SECTION_PERSONAL, before=F.APPLICATION_INTRO)
    form.question("First Name", person.first_name)
    form.question("Last Name", person.last_name)
    form.question("Please indicate which country you are based in.", person.based_in)
    form.question("Please select your country of residence.", person.country_of_residence)
    form.question("Country of citizenship", person.country_of_citizenship)
    form.question("Do you have dual citizenship?", _yes_no(person.dual_citizenship))
    form.question(
        "What city would be most convenient for you to attend a physical interview?",
        person.interview_city,
        F.HELP_INTERVIEW_CITY,
    )
    form.question("Gender", person.gender, F.HELP_GENDER)
    form.question("Date of Birth", _fmt_date(person.date_of_birth))
    form.question("Email", person.email, F.HELP_EMAIL)
    form.question("Phone Number", person.phone, F.HELP_PHONE)
    form.question("LinkedIn URL", person.linkedin_url, F.HELP_LINKEDIN)
    form.question("How did you hear about MEST?", person.heard_about)
    if person.heard_about == "Referral":
        form.question("Referral source", person.referral_source)
        form.question("Referrer's name", person.referrer_name)
        form.question("Referrer's email", person.referrer_email)
        form.question("Referrer's contact number", person.referrer_phone)
    form.question("Have you applied to MEST in the past?", _yes_no(person.applied_before))
    form.question(
        "Have you previously participated in any programs run by MEST or its partners?",
        _yes_no(person.participated_before),
        rule=False,
    )

    form.section(*F.SECTION_EDUCATION)
    for education in app.education:
        form.question("Highest degree in progress/completed", education.degree)
        form.question("Major/Field of study", education.major, F.HELP_MAJOR)
        form.question("University/Institution", education.institution, F.HELP_INSTITUTION)
        if education.institution == "Other":
            form.question("If Other - please specify your institution", education.institution_other)
        form.question("Location", education.location)
        form.question("Graduation Date", _fmt_date(education.graduation_date))
        form.question(
            "List any other relevant training or certification programs you have completed",
            education.other_training,
        )
    form.question("Add another degree?", "No")

    form.section(*F.SECTION_WORK)
    for index, experience in enumerate(app.experience):
        _experience_block(form, experience, first=index == 0, more=index + 1 < len(app.experience))

    form.section(*F.SECTION_STATEMENTS)
    video = uploads["personal_statement_video"]
    form.upload(
        [(text, FONT) for text in F.VIDEO_PROMPT],
        video.link_text, video.filename, video.size_bytes, video.url,
    )

    form.section(*F.SECTION_ESSAYS)
    for index, essay in enumerate(app.essays):
        form.question(essay.question, essay.answer, rule=index + 1 < len(app.essays))

    form.section(F.SECTION_RESUME[0])
    resume = uploads["resume"]
    if resume is None:
        form.question(F.RESUME_PROMPT, None)
    else:
        form.upload(
            [(F.RESUME_PROMPT, FONT)], resume.link_text, resume.filename, resume.size_bytes, resume.url
        )
    for index, item in enumerate(evidence):
        paragraphs = [(text, FONT) for text in F.EVIDENCE_PROMPT] if index == 0 else []
        paragraphs.append((item.label, BOLD if index == 0 else FONT))
        form.upload(paragraphs, item.link_text, item.filename, item.size_bytes, item.url)
    form.question(
        F.EVIDENCE_URLS_PROMPT[0],
        "\n".join(app.evidence_urls) or None,
        F.EVIDENCE_URLS_PROMPT[1],
    )

    form.section(*F.SECTION_REFERENCES)
    for position, reference in enumerate(app.references):
        form.section(f"{reference.kind.capitalize()} reference")
        form.question("Full Name", reference.full_name, F.HELP_REFERENCE_NAME[reference.kind])
        form.question("Title/Position", reference.title)
        form.question("Relationship", reference.relationship, F.HELP_RELATIONSHIP)
        form.question("Contact number", reference.phone, F.HELP_REFERENCE_PHONE)
        form.question("Email", reference.email, F.HELP_EMAIL, rule=position + 1 < len(app.references))

    # --- Test et vidéo de réflexion ---------------------------------------------
    assessment = tasks[F.TASK_ASSESSMENT]
    form.task(assessment.title, assessment.status, assessment.completed_on)
    form.black_paragraphs(F.ASSESSMENT_TEXT)

    reflection_task = tasks[F.TASK_REFLECTION]
    reflection = uploads["reflection_video"]
    form.task(reflection_task.title, reflection_task.status, reflection_task.completed_on, room=330.0)
    form.upload(
        [(text, FONT) for text in F.REFLECTION_TEXT],
        reflection.link_text, reflection.filename, reflection.size_bytes, reflection.url,
        rule=False, task_style=True,
    )
    return form


# --------------------------------------------------------------------------
# Pièces jointes
# --------------------------------------------------------------------------


def _resume_page(pdf: canvas.Canvas, dossier: Dossier) -> None:
    app, resume = dossier.application, dossier.resume
    person = app.personal
    width, height = A4
    pdf.setPageSize(A4)
    pdf.setFillColorRGB(*BLACK)
    y = height - 70

    def line(text: str, font: str = FONT, size: float = 10.0, gap: float = 15.0, indent: float = 0.0) -> None:
        nonlocal y
        for part in simpleSplit(text, font, size, width - 100 - indent):
            pdf.setFont(font, size)
            pdf.drawString(50 + indent, y, part)
            y -= gap

    def heading(text: str) -> None:
        nonlocal y
        y -= 8
        line(text, BOLD, 11.0, 17.0)

    line(f"{person.first_name} {person.last_name}", BOLD, 22.0, 24.0)
    line(resume.headline, FONT, 12.0, 18.0)
    line(f"{person.email} | {person.phone} | {person.linkedin_url}", FONT, 9.0)
    heading("EDUCATION")
    for education in app.education:
        institution = education.institution_other or education.institution
        line(f"{education.degree}, {education.major}", BOLD)
        line(f"{institution}, {education.location} - {education.graduation_date.year}")
        if education.other_training:
            line(f"Training: {education.other_training}")
    heading("PROFESSIONAL EXPERIENCE")
    for experience, bullets in zip(app.experience, resume.bullets):
        end = "Present" if experience.current else f"{experience.end_date:%b %Y}"
        line(f"{experience.job_title}, {experience.organisation}", BOLD)
        line(f"{experience.location} | {experience.start_date:%b %Y} - {end}")
        for bullet in bullets:
            line(f"- {bullet}", indent=10.0)
    heading("SKILLS")
    line(resume.skills)
    heading("LANGUAGES")
    line(", ".join(resume.languages))
    pdf.showPage()


def _certificate_image(certificate: Certificate, name: str) -> Image.Image:
    """Certificat rendu comme une image : son texte n'est lisible que par OCR."""
    image = Image.new("RGB", (1600, 1130), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 1570, 1100), outline=(20, 50, 100), width=14)
    rows = [
        (certificate.title.upper(), 76, 190),
        ("This certificate is presented to", 34, 380),
        (name, 92, 470),
        (f"for {certificate.subject}", 40, 680),
        (f"Issued in {certificate.issued}", 32, 860),
    ]
    for text, size, top in rows:
        font = ImageFont.load_default(size=size)
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((1600 - (box[2] - box[0])) / 2, top), text, fill=(15, 25, 60), font=font)
    return image


def _certificate_page(pdf: canvas.Canvas, certificate: Certificate, name: str) -> None:
    width, height = landscape(A4)
    pdf.setPageSize((width, height))
    if certificate.as_image:
        buffer = io.BytesIO()
        _certificate_image(certificate, name).save(buffer, format="PNG")
        buffer.seek(0)
        pdf.drawImage(ImageReader(buffer), 0, 0, width=width, height=height)
    else:
        pdf.setFillColorRGB(*BLACK)
        rows = [
            (certificate.title, BOLD, 30.0, 150),
            ("This certificate is presented to", FONT, 14.0, 230),
            (name, BOLD, 34.0, 290),
            (f"for {certificate.subject}", FONT, 16.0, 370),
            (f"Issued in {certificate.issued}", FONT, 12.0, 450),
        ]
        for text, font, size, top in rows:
            pdf.setFont(font, size)
            pdf.drawCentredString(width / 2, height - top, text)
    pdf.showPage()


def render_dossier(dossier: Dossier, path: str | Path) -> int:
    """Écrit le PDF d'un dossier fictif et renvoie son nombre de pages de formulaire."""
    app = dossier.application
    pdf = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    pdf.setTitle(f"Application {app.application_id}")
    pdf.setAuthor("Générateur de dossiers fictifs")
    form_pages = _build_form(app).draw(pdf)
    if dossier.resume is not None:
        _resume_page(pdf, dossier)
    name = f"{app.personal.first_name} {app.personal.last_name}"
    for certificate in dossier.certificates:
        _certificate_page(pdf, certificate, name)
    pdf.save()
    return form_pages
