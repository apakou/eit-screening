"""Import d'un dossier de candidature exporté en PDF depuis SurveyMonkey Apply.

L'export suit une grammaire visuelle stable, sur laquelle s'appuie ce module
plutôt que sur le texte des questions :

- une réponse est écrite dans un rectangle gris ;
- le libellé de la question est le texte placé juste au-dessus ;
- un trait fin sépare deux questions ;
- un fichier envoyé apparaît comme un lien bleu suivi d'une ligne
  « Filename: … Size: … » ;
- les pages du formulaire portent un pied de page « 3 / 16 » ; les pages
  suivantes sont les pièces jointes (CV, certificats).

Le formulaire entier est conservé dans ``Application.items``. Les champs
connus sont en plus rangés dans des structures typées (identité, formation,
expériences, réponses libres, fichiers, références).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from ..models import (
    Application,
    AttachmentPage,
    Education,
    EligibilityAnswer,
    Essay,
    FormItem,
    Reference,
    TaskStatus,
    UploadedFile,
    WorkExperience,
)

NO_RESPONSE = "(No response)"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv")

_FOOTER_RE = re.compile(r"^(\d+) / (\d+)$")
_FILE_META_RE = re.compile(
    r"^Filename:\s*(?P<name>.+?)\s+Size:\s*(?P<size>[\d.,]+)\s*(?P<unit>bytes|B|kB|KB|MB|GB)$"
)
_STATUS_RE = re.compile(r"^(?P<status>[A-Za-z][A-Za-z ]*?)(?:\s+-\s+(?P<date>.+))?$")
_URL_RE = re.compile(r"https?://\S+")
_SIZE_UNITS = {"bytes": 1, "B": 1, "kB": 1_000, "KB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000}

# Clé stable de chaque question d'éligibilité, repérée par un fragment de son libellé.
ELIGIBILITY_KEYS: list[tuple[str, str]] = [
    ("citizen_of_region", r"citizen of a country in"),
    ("age_in_range", r"between the ages of"),
    ("has_degree", r"hold a degree"),
    ("software_experience", r"experience in software development"),
    ("ready_to_launch", r"ready and committed to launching"),
    ("ai_business", r"aspire to launch an AI"),
    ("willing_to_cofound", r"co-found"),
    ("full_time_commitment", r"pause or leave your current"),
    ("can_relocate", r"able to relocate"),
    ("communal_housing", r"communal housing"),
]

_PERSONAL_FIELDS = {
    "first name": "first_name",
    "last name": "last_name",
    "please indicate which country you are based in.": "based_in",
    "please select your country of residence.": "country_of_residence",
    "country of citizenship": "country_of_citizenship",
    "do you have dual citizenship?": "dual_citizenship",
    "what city would be most convenient for you to attend a physical interview?": "interview_city",
    "gender": "gender",
    "date of birth": "date_of_birth",
    "email": "email",
    "phone number": "phone",
    "linkedin url": "linkedin_url",
    "how did you hear about mest?": "heard_about",
    "referral source": "referral_source",
    "referrer's name": "referrer_name",
    "referrer's email": "referrer_email",
    "referrer's contact number": "referrer_phone",
    "have you applied to mest in the past?": "applied_before",
    "have you previously participated in any programs run by mest or its partners?": "participated_before",
}
_EDUCATION_FIELDS = {
    "highest degree in progress/completed": "degree",
    "major/field of study": "major",
    "university/institution": "institution",
    "if other - please specify your institution": "institution_other",
    "location": "location",
    "graduation date": "graduation_date",
    "list any other relevant training or certification programs you have completed": "other_training",
}
_EXPERIENCE_FIELDS = {
    "organisation name": "organisation",
    "job title": "job_title",
    "start date": "start_date",
    "end date": "end_date",
    "location": "location",
    "do you still work here?": "current",
    "total duration (in months)": "duration_months",
}
_REFERENCE_FIELDS = {
    "full name": "full_name",
    "title/position": "title",
    "relationship": "relationship",
    "contact number": "phone",
    "email": "email",
}
_BOOLEAN_FIELDS = {"dual_citizenship", "applied_before", "participated_before", "current"}
_DATE_FIELDS = {"date_of_birth", "graduation_date", "start_date", "end_date"}


# --------------------------------------------------------------------------
# Lecture bas niveau : lignes de texte, zones de réponse, séparateurs
# --------------------------------------------------------------------------


@dataclass
class _Line:
    page: int
    top: float
    bottom: float
    x0: float
    x1: float
    text: str
    size: float
    bold: bool
    rgb: tuple[float, float, float] | None


@dataclass
class _Element:
    kind: str  # app_title, task_heading, form_title, status, label, answer, separator, link, filemeta
    page: int
    top: float
    text: str = ""
    lines: list[_Line] = field(default_factory=list)
    url: str | None = None


def _rgb(color) -> tuple[float, float, float] | None:
    """Ramène une couleur PDF (gris, RVB ou CMJN) à un triplet RVB."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        return (float(color),) * 3
    values = tuple(float(v) for v in color)
    if len(values) == 1:
        return values * 3
    if len(values) == 3:
        return values
    if len(values) == 4:
        c, m, y, k = values
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _is_light_grey(rgb) -> bool:
    return rgb is not None and max(rgb) - min(rgb) < 0.02 and 0.85 <= rgb[0] <= 0.98


def _is_blue(rgb) -> bool:
    return rgb is not None and rgb[2] > 0.6 and rgb[0] < 0.3 and rgb[1] < 0.3


def _is_black(rgb) -> bool:
    return rgb is None or max(rgb) < 0.05


def _paragraphs(lines: list[_Line]) -> list[str]:
    """Regroupe des lignes en paragraphes d'après l'espace vertical entre elles."""
    paragraphs: list[list[str]] = []
    previous: _Line | None = None
    for line in lines:
        new_paragraph = previous is None or line.page != previous.page
        if not new_paragraph:
            # Interligne de 20 pt pour le texte gris du formulaire, de 11 pt pour le texte noir.
            limit = 16.0 if _is_black(previous.rgb) else 23.0
            new_paragraph = line.top - previous.top > limit
        if new_paragraph:
            paragraphs.append([])
        paragraphs[-1].append(line.text)
        previous = line
    return [" ".join(parts) for parts in paragraphs]


def _read_page(page, number: int) -> tuple[list[_Element], tuple[int, int] | None]:
    """Transforme une page en éléments ordonnés de haut en bas."""
    boxes, separators = [], []
    for rect in page.rects:
        if not rect.get("fill") or not _is_light_grey(_rgb(rect.get("non_stroking_color"))):
            continue
        height = rect["bottom"] - rect["top"]
        if height >= 8:
            boxes.append(rect)
        elif rect["x1"] - rect["x0"] > 200:
            separators.append(rect)

    lines: list[_Line] = []
    for raw in page.extract_text_lines(return_chars=True):
        text = raw["text"].strip()
        if not text:
            continue
        first = raw["chars"][0]
        lines.append(
            _Line(
                page=number,
                top=raw["top"],
                bottom=raw["bottom"],
                x0=raw["x0"],
                x1=raw["x1"],
                text=text,
                size=float(first["size"]),
                bold="bold" in first["fontname"].lower(),
                rgb=_rgb(first.get("non_stroking_color")),
            )
        )

    footer = None
    elements: list[_Element] = []
    boxed: dict[int, list[_Line]] = {index: [] for index in range(len(boxes))}
    for line in lines:
        middle = (line.top + line.bottom) / 2
        match = _FOOTER_RE.match(line.text)
        if match and line.top > page.height - 45:
            footer = (int(match.group(1)), int(match.group(2)))
            continue
        box_index = next(
            (i for i, box in enumerate(boxes) if box["top"] - 1 <= middle <= box["bottom"] + 1),
            None,
        )
        if box_index is not None:
            boxed[box_index].append(line)
            continue
        elements.append(_classify(line, page))

    for index, box in enumerate(boxes):
        box_lines = sorted(boxed[index], key=lambda item: item.top)
        elements.append(
            _Element(
                kind="answer",
                page=number,
                top=box["top"],
                text="\n".join(_paragraphs(box_lines)),
                lines=box_lines,
            )
        )
    for rect in separators:
        elements.append(_Element(kind="separator", page=number, top=rect["top"]))

    elements.sort(key=lambda element: element.top)
    return elements, footer


def _classify(line: _Line, page) -> _Element:
    base = dict(page=line.page, top=line.top, text=line.text, lines=[line])
    if _is_blue(line.rgb):
        url = None
        for link in page.hyperlinks:
            if abs(link["top"] - line.top) < 8 and link.get("uri"):
                url = link["uri"]
                break
        return _Element(kind="link", url=url, **base)
    if _FILE_META_RE.match(line.text):
        return _Element(kind="filemeta", **base)
    if line.size >= 19:
        return _Element(kind="app_title", **base)
    if line.size >= 16.5:
        return _Element(kind="form_title", **base)
    if line.bold and line.size >= 13.5:
        return _Element(kind="task_heading", **base)
    if line.bold and line.size < 9.5:
        return _Element(kind="status", **base)
    return _Element(kind="label", **base)


# --------------------------------------------------------------------------
# Conversions de valeurs
# --------------------------------------------------------------------------


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if not value or value == NO_RESPONSE else value


def _to_bool(value: str | None) -> bool | None:
    value = (_clean(value) or "").lower()
    return {"yes": True, "no": False}.get(value)


def _to_date(value: str | None) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    for pattern in ("%b %d %Y", "%B %d %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _to_datetime(value: str | None) -> datetime | None:
    value = _clean(value)
    if value is None:
        return None
    value = re.sub(r"\s*\([A-Z]+\)$", "", value)
    for pattern in ("%b %d %Y %I:%M %p", "%B %d %Y %I:%M %p", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def _to_int(value: str | None) -> int | None:
    value = _clean(value)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _size_to_bytes(size: str, unit: str) -> int:
    return int(round(float(size.replace(",", "")) * _SIZE_UNITS[unit]))


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).replace("’", "'")


def _upload_kind(task: str, block_text: str, last_paragraph: str, filename: str) -> str:
    lowered = block_text.lower()
    if re.fullmatch(r"evidence \d+", last_paragraph.strip().lower()):
        return "evidence"
    if "resume" in lowered or "résumé" in lowered or "curriculum" in lowered:
        return "resume"
    if "reflection" in task.lower():
        return "reflection_video"
    if "video" in lowered or filename.lower().endswith(VIDEO_EXTENSIONS):
        return "personal_statement_video"
    return "other"


# --------------------------------------------------------------------------
# Du flux d'éléments au formulaire brut
# --------------------------------------------------------------------------


def _parse_header(app: Application, title: str, block: list[_Line]) -> None:
    match = re.search(r"Application:\s*(\S+)", title)
    if match:
        app.application_id = match.group(1)
    plain: list[str] = []
    for line in block:
        text = line.text
        if text.startswith("ID:"):
            app.application_id = text.split(":", 1)[1].strip() or app.application_id
        elif text.startswith("Last submitted:"):
            app.last_submitted = _to_datetime(text.split(":", 1)[1])
        elif text.startswith("Labels:"):
            labels = text.split(":", 1)[1]
            app.labels = [label.strip() for label in labels.split(",") if label.strip()]
        elif text != "Summary":
            plain.append(text)
    if plain:
        name, _, email = plain[0].rpartition(" - ")
        app.applicant_display_name = (name or plain[0]).strip()
        app.applicant_email = email.strip() if name else None
    if len(plain) > 1:
        app.program = plain[1]


def _build_items(app: Application, elements: list[_Element]) -> None:
    task = ""
    section: str | None = None
    block: list[_Line] = []
    app_title = ""
    after_heading = False
    pending_link: _Element | None = None
    previous_kind = ""
    previous_page = 0

    def flush_as_section() -> None:
        nonlocal section, block
        if block:
            paragraphs = _paragraphs(block)
            short = [p for p in paragraphs if len(p.split()) <= 6]
            section = (short or paragraphs)[0]
        block = []

    for element in elements:
        kind = element.kind
        if kind == "app_title":
            app_title = element.text
        elif kind == "task_heading":
            if not app.tasks:
                _parse_header(app, app_title, block)
                block = []
            else:
                flush_as_section()
            task, section, pending_link = element.text, None, None
            app.tasks.append(TaskStatus(title=task))
            after_heading = True
        elif kind == "status":
            match = _STATUS_RE.match(element.text)
            if app.tasks and match and app.tasks[-1].status is None:
                app.tasks[-1].status = match.group("status").strip()
                app.tasks[-1].completed_on = _to_date(match.group("date"))
            else:
                block.extend(element.lines)
        elif kind == "form_title":
            after_heading = True
        elif kind == "label":
            block.extend(element.lines)
        elif kind == "separator":
            flush_as_section()
            after_heading = False
        elif kind == "answer":
            continuation = (
                not block
                and previous_kind == "answer"
                and element.page != previous_page
                and app.items
            )
            if continuation:
                # Réponse longue coupée par un saut de page.
                last = app.items[-1]
                last.answer = " ".join(part for part in (last.answer, element.text) if part)
            else:
                paragraphs = _paragraphs(block)
                if not paragraphs:
                    app.warnings.append(
                        f"Réponse sans question page {element.page} : {element.text[:40]!r}"
                    )
                    paragraphs = [""]
                if after_heading and len(paragraphs) > 1:
                    # Juste après un titre, le texte d'introduction précède la question.
                    question, help_text = paragraphs[-1], None
                else:
                    question, help_text = paragraphs[0], "\n".join(paragraphs[1:]) or None
                app.items.append(
                    FormItem(
                        task=task,
                        section=section,
                        question=question,
                        help_text=help_text,
                        answer=_clean(element.text),
                    )
                )
            block = []
            after_heading = False
        elif kind == "link":
            pending_link = element
        elif kind == "filemeta":
            meta = _FILE_META_RE.match(element.text)
            paragraphs = _paragraphs(block) or [""]
            filename = meta.group("name")
            file_kind = _upload_kind(task, " ".join(paragraphs), paragraphs[-1], filename)
            label = paragraphs[-1] if file_kind == "evidence" else paragraphs[0]
            if after_heading and file_kind != "evidence":
                label = task
            upload = UploadedFile(
                kind=file_kind,
                label=label,
                link_text=pending_link.text if pending_link else filename,
                filename=filename,
                size_bytes=_size_to_bytes(meta.group("size"), meta.group("unit")),
                url=pending_link.url if pending_link else None,
            )
            app.items.append(
                FormItem(
                    task=task,
                    section=section,
                    question=label,
                    help_text="\n".join(p for p in paragraphs if p and p != label) or None,
                    file=upload,
                )
            )
            block, pending_link, after_heading = [], None, False
        previous_kind, previous_page = kind, element.page

    if not app.tasks:
        _parse_header(app, app_title, block)


# --------------------------------------------------------------------------
# Du formulaire brut aux champs typés
# --------------------------------------------------------------------------


def _convert(field_name: str, value: str | None):
    if field_name in _BOOLEAN_FIELDS:
        return _to_bool(value)
    if field_name in _DATE_FIELDS:
        return _to_date(value)
    if field_name == "duration_months":
        return _to_int(value)
    return _clean(value)


def _structure(app: Application) -> None:
    education: Education | None = None
    experience: WorkExperience | None = None
    references: dict[str, Reference] = {}

    for item in app.items:
        if item.file is not None:
            app.uploads.append(item.file)
            continue

        question = _norm(item.question)
        section = _norm(item.section)
        task = _norm(item.task)

        if "eligibility" in task:
            if question in ("first name", "last name"):
                continue
            key = next(
                (k for k, pattern in ELIGIBILITY_KEYS if re.search(pattern, item.question, re.I)),
                None,
            )
            app.eligibility.append(
                EligibilityAnswer(key=key, question=item.question, answer=_to_bool(item.answer))
            )
        elif "reference" in section and section.split()[0] in ("professional", "academic"):
            kind = section.split()[0]
            reference = references.setdefault(kind, Reference(kind=kind))
            field_name = _REFERENCE_FIELDS.get(question)
            if field_name:
                setattr(reference, field_name, _clean(item.answer))
            else:
                app.warnings.append(f"Question non reconnue (références) : {item.question}")
        elif "education" in section:
            if question == "add another degree?":
                education = None
                continue
            field_name = _EDUCATION_FIELDS.get(question)
            if field_name is None:
                app.warnings.append(f"Question non reconnue (formation) : {item.question}")
                continue
            if education is None or field_name == "degree":
                education = Education()
                app.education.append(education)
            setattr(education, field_name, _convert(field_name, item.answer))
        elif "work experience" in section:
            if question == "add another experience?":
                experience = None
                continue
            field_name = _EXPERIENCE_FIELDS.get(question)
            if field_name is None:
                app.warnings.append(f"Question non reconnue (expérience) : {item.question}")
                continue
            if experience is None or field_name == "organisation":
                experience = WorkExperience()
                app.experience.append(experience)
            setattr(experience, field_name, _convert(field_name, item.answer))
        elif "free form" in section:
            answer = _clean(item.answer)
            app.essays.append(
                Essay(
                    question=item.question,
                    answer=answer,
                    word_count=len(answer.split()) if answer else 0,
                )
            )
        elif "evidence" in section and "form of a link" in question:
            app.evidence_urls = _URL_RE.findall(item.answer or "")
        elif "upload" in question:
            # Question d'envoi de fichier restée sans réponse.
            app.warnings.append(f"Fichier non fourni : {item.question}")
        else:
            field_name = _PERSONAL_FIELDS.get(question)
            if field_name:
                setattr(app.personal, field_name, _convert(field_name, item.answer))
            else:
                app.warnings.append(f"Question non reconnue : {item.question}")

    app.references = [references[kind] for kind in ("professional", "academic") if kind in references]


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------


def parse_application(path: str | Path) -> Application:
    """Lit un export PDF SurveyMonkey Apply et renvoie le dossier structuré."""
    app = Application(application_id="")
    elements: list[_Element] = []
    with pdfplumber.open(path) as pdf:
        pages = [(_read_page(page, number), page) for number, page in enumerate(pdf.pages, 1)]
        has_footers = any(footer is not None for (_, footer), _ in pages)
        if not has_footers:
            app.warnings.append(
                "Aucun pied de page « n / N » : toutes les pages sont lues comme formulaire."
            )
        for number, ((page_elements, footer), page) in enumerate(pages, 1):
            if footer is not None or not has_footers:
                elements.extend(page_elements)
                app.form_page_count += 1
            else:
                text = (page.extract_text() or "").strip()
                app.attachment_pages.append(
                    AttachmentPage(
                        page_number=number,
                        text=text,
                        needs_ocr=len(text) < 20,
                        image_count=len(page.images),
                    )
                )
    _build_items(app, elements)
    _structure(app)
    if not app.application_id:
        app.warnings.append("Numéro de candidature introuvable.")
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convertit un export PDF SurveyMonkey Apply en dossier structuré (JSON)."
    )
    parser.add_argument("pdf", type=Path, help="Export PDF de la candidature")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON de sortie (défaut : écran)")
    parser.add_argument(
        "--sans-brut",
        action="store_true",
        help="Ne pas inclure la liste brute des questions et réponses",
    )
    args = parser.parse_args(argv)

    application = parse_application(args.pdf)
    exclude = {"items"} if args.sans_brut else None
    payload = application.model_dump_json(indent=2, exclude=exclude)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    for warning in application.warnings:
        print(f"Attention : {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
