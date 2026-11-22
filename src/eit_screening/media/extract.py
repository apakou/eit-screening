"""Extraction du contenu des pièces jointes et des vidéos d'un dossier.

Pour chaque ``application.pdf``, écrit ``extraction.json`` à côté : pages de
pièces jointes relues par Docling (OCR compris) et transcriptions des deux
vidéos. L'anonymisation lit ce fichier s'il existe.

Vidéos : l'export ne contient que des liens protégés ; le module ne les
télécharge jamais. Il cherche à côté du PDF un fichier nommé selon la
convention de ``media.toml`` (``personal_statement.mp4``…). À défaut, il lit la
transcription écrite (``personal_statement.txt``), comme pour les dossiers
fictifs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .. import __version__
from ..models import AttachmentPage
from ..screening.common import git_commit, plain_text
from .config import MediaConfig, load_config
from .transcribe import Transcript, read_text_transcript, transcribe_video

EXTRACTION_FILE = "extraction.json"
SECTIONS = ("personal_statement", "assessment_reflection")


class Extraction(BaseModel):
    attachment_pages: list[AttachmentPage] = Field(default_factory=list)
    transcripts: dict[str, Transcript] = Field(default_factory=dict)


def find_video(folder: Path, section: str, config: MediaConfig) -> Path | None:
    stem = getattr(config.videos, section)
    for extension in config.videos.extensions:
        path = folder / f"{stem}{extension}"
        if path.exists():
            return path
    return None


def transcripts_for(folder: Path, config: MediaConfig) -> dict[str, Transcript]:
    """Transcription de chaque vidéo : par Whisper si la vidéo est là, sinon depuis le fichier texte."""
    found: dict[str, Transcript] = {}
    for section in SECTIONS:
        video = find_video(folder, section, config)
        if video is not None:
            found[section] = transcribe_video(video, config)
        elif (folder / f"{section}.txt").exists():
            found[section] = read_text_transcript(folder / f"{section}.txt")
    return found


def load_extraction(folder: Path) -> Extraction | None:
    path = folder / EXTRACTION_FILE
    if not path.exists():
        return None
    return Extraction.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Mesure sur les dossiers fictifs : texte attendu des certificats
# --------------------------------------------------------------------------


class CertificateCheck(BaseModel):
    page_number: int
    as_image: bool
    similarity: float
    lines_found: int
    lines_expected: int
    name_exact: bool
    name_words_found: bool


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", plain_text(text))


def check_certificates(pages: list[AttachmentPage], truth: list[dict]) -> list[CertificateCheck]:
    """Compare le texte relu de chaque certificat au texte attendu (``pieces_jointes.json``)."""
    from rapidfuzz import fuzz

    by_number = {page.page_number: page for page in pages}
    checks = []
    for expected in truth:
        if expected["kind"] != "certificate":
            continue
        page = by_number.get(expected["page_number"])
        got = _norm(page.text if page else "")
        lines = [_norm(line) for line in expected["lines"]]
        checks.append(
            CertificateCheck(
                page_number=expected["page_number"],
                as_image=expected["as_image"],
                similarity=round(fuzz.ratio(got, " ".join(lines)), 1),
                lines_found=sum(1 for line in lines if line and line in got),
                lines_expected=len(lines),
                # Le nom du candidat est la 3e ligne : il doit être lu à l'identique pour être masqué.
                name_exact=bool(lines[2]) and re.search(rf"(?<!\w){re.escape(lines[2])}(?!\w)", got) is not None,
                name_words_found=bool(lines[2]) and all(
                    re.search(rf"(?<!\w){re.escape(word)}(?!\w)", got) for word in lines[2].split()
                ),
            )
        )
    return checks


# --------------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Relit les pièces jointes (Docling, OCR) et transcrit les vidéos ; écrit extraction.json."
    )
    parser.add_argument("dossiers", type=Path, help="Dossier parcouru récursivement à la recherche de application.pdf")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML (défaut : media.toml)")
    parser.add_argument("--sans-ocr", action="store_true", help="Ne relit pas les pièces jointes (transcriptions seules)")
    parser.add_argument("-o", "--out", type=Path, help="Fichier JSON du résumé et des mesures")
    args = parser.parse_args(argv)

    from ..ingestion.smapply_pdf import parse_application
    from .attachments import read_attachments

    config = load_config(args.config)
    paths = sorted(args.dossiers.rglob("application.pdf"))
    if not paths:
        print(f"Aucun fichier application.pdf trouvé dans {args.dossiers}.", file=sys.stderr)
        return 1

    print(f"{'Numéro':<12} {'Pages':>5} {'OCR':>4} {'Durée':>6}  {'Certificats image (similarité, nom exact)':<44} Transcriptions")
    all_checks: list[CertificateCheck] = []
    timings: list[float] = []
    for path in paths:
        folder = path.parent
        app = parse_application(path)
        started = time.perf_counter()
        pages = app.attachment_pages if args.sans_ocr else read_attachments(path, app, config)
        transcripts = transcripts_for(folder, config)
        elapsed = time.perf_counter() - started
        timings.append(elapsed)
        extraction = Extraction(attachment_pages=pages, transcripts=transcripts)
        (folder / EXTRACTION_FILE).write_text(extraction.model_dump_json(indent=2), encoding="utf-8")

        checks: list[CertificateCheck] = []
        truth_path = folder / "pieces_jointes.json"
        if truth_path.exists():
            checks = check_certificates(pages, json.loads(truth_path.read_text(encoding="utf-8")))
            all_checks += checks
        images = ", ".join(
            f"p.{c.page_number} {c.similarity:g} {'oui' if c.name_exact else 'NON'}" for c in checks if c.as_image
        ) or "-"
        spoken = ", ".join(
            f"{section.split('_')[0]} ({t.source}, {len(t.segments)} seg.)" for section, t in transcripts.items()
        ) or "-"
        ocr = sum(page.text_source == "ocr" for page in pages)
        print(f"{app.application_id:<12} {len(pages):>5} {ocr:>4} {elapsed:>5.1f}s  {images:<44} {spoken}")

    images = [c for c in all_checks if c.as_image]
    texts = [c for c in all_checks if not c.as_image]
    print(f"\n{len(paths)} dossiers ; durée moyenne par dossier : {sum(timings) / len(timings):.1f} s.")
    summary: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_commit": git_commit(),
        "ocr_engine": None if args.sans_ocr else config.attachments.ocr_engine,
        "whisper_model": config.transcription.model,
        "dossiers": len(paths),
        "seconds_per_dossier": round(sum(timings) / len(timings), 2),
    }
    for label, group in (("image", images), ("texte", texts)):
        if not group:
            continue
        lines = sum(c.lines_found for c in group)
        expected = sum(c.lines_expected for c in group)
        names = sum(c.name_exact for c in group)
        words = sum(c.name_words_found for c in group)
        mean = sum(c.similarity for c in group) / len(group)
        print(
            f"Certificats {label} : {len(group)} ; similarité moyenne {mean:.1f}/100 ; "
            f"lignes retrouvées à l'identique {lines}/{expected} ; nom du candidat exact {names}/{len(group)}, "
            f"chaque mot du nom lu (ordre libre) {words}/{len(group)}."
        )
        summary[f"certificates_{label}"] = {
            "count": len(group), "mean_similarity": round(mean, 1),
            "lines_exact": lines, "lines_expected": expected, "name_exact": names, "name_words_found": words,
        }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Résumé écrit dans {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
