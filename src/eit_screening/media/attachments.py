"""Lecture des pièces jointes (CV, certificats) avec Docling, OCR compris.

Les pièces jointes sont les pages ajoutées après le formulaire dans l'export
PDF. L'import (pdfplumber) en lit déjà le texte, mais ne voit rien dans un
certificat scanné : ces pages sont marquées ``needs_ocr``. Docling relit toutes
les pages de pièces jointes, avec reconnaissance de caractères pour les images.

Docling et ses modèles sont lourds : ils ne sont chargés qu'au premier appel.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from ..models import AttachmentPage, Application
from .config import AttachmentRule, MediaConfig, load_config


@cache
def _converter(engine: str, languages: tuple[str, ...]):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(do_ocr=True, do_table_structure=False)
    if engine == "tesseract":
        options.ocr_options = TesseractCliOcrOptions(lang=list(languages))
    elif engine == "rapidocr":
        options.ocr_options = RapidOcrOptions()
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def _texts_by_page(pdf_path: Path, first: int, last: int, rule: AttachmentRule) -> dict[int, str]:
    """Texte de chaque page lue par Docling, dans l'ordre de lecture. Les numéros de page sont ceux du PDF."""
    converter = _converter(rule.ocr_engine, tuple(rule.tesseract_languages))
    document = converter.convert(str(pdf_path), page_range=(first, last)).document
    pages: dict[int, list[str]] = {}
    for item, _ in document.iterate_items():
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue
        for prov in getattr(item, "prov", None) or []:
            pages.setdefault(prov.page_no, []).append(text)
            break
    return {page: "\n".join(lines) for page, lines in pages.items()}


def read_attachments(
    pdf_path: Path | str, app: Application, config: MediaConfig | None = None
) -> list[AttachmentPage]:
    """Pages de pièces jointes relues par Docling.

    Une page marquée ``needs_ocr`` prend la source ``ocr``. Si Docling ne
    renvoie rien pour une page, le texte de l'import est gardé (source ``pdf``).
    """
    config = config or load_config()
    if not app.attachment_pages:
        return []
    numbers = [page.page_number for page in app.attachment_pages]
    texts = _texts_by_page(Path(pdf_path), min(numbers), max(numbers), config.attachments)
    pages: list[AttachmentPage] = []
    for page in app.attachment_pages:
        text = texts.get(page.page_number, "")
        if text:
            source = "ocr" if page.needs_ocr else "docling"
            pages.append(page.model_copy(update={"text": text, "text_source": source}))
        else:
            pages.append(page.model_copy())
    return pages
