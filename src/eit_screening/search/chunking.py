"""Découpage des dossiers anonymisés en passages qui gardent leur provenance.

Un dossier anonymisé est une liste de textes (« unités ») : une réponse libre,
une page de pièce jointe, un segment de transcription… Un passage est :

- soit une tranche d'une seule unité (``unit_start == unit_end``), entre les
  positions ``char_start`` et ``char_end`` du texte anonymisé de cette unité ;
- soit, pour une transcription horodatée, une suite de segments entiers
  (``unit_start`` à ``unit_end``), qui garde le début du premier segment et la
  fin du dernier.

``passage_text`` reconstruit le texte d'un passage à partir du dossier : c'est
ce qui permet de retrouver son emplacement exact. Les positions se rapportent
au texte anonymisé ; dans le dossier d'origine, l'emplacement est donné par la
section, la question, la page ou l'horodatage.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel

from ..privacy.anonymize import AnonymizedDossier
from .config import ChunkingRule

# Espace de noms des identifiants de passage (uuid5) : même passage, même identifiant.
PASSAGE_NAMESPACE = uuid.UUID("6f1d3c0e-8a52-4f0b-9a64-3f6f0e5b2c11")
TIMESTAMPED = {"personal_statement", "assessment_reflection"}
SEGMENT_JOIN = " "


class Passage(BaseModel):
    id: str
    pseudonym: str
    section: str
    label: str | None = None
    page: int | None = None
    start: float | None = None  # secondes, transcriptions horodatées seulement
    end: float | None = None
    unit_start: int
    unit_end: int
    char_start: int
    char_end: int
    text: str


def _passage_id(pseudonym: str, unit_start: int, char_start: int, unit_end: int, char_end: int) -> str:
    return str(uuid.uuid5(PASSAGE_NAMESPACE, f"{pseudonym}:{unit_start}:{char_start}:{unit_end}:{char_end}"))


def passage_text(passage: Passage, dossier: AnonymizedDossier) -> str:
    """Texte du passage, relu dans le dossier anonymisé à partir de sa provenance."""
    texts = dossier.texts
    if passage.unit_start == passage.unit_end:
        return texts[passage.unit_start].text[passage.char_start:passage.char_end]
    parts = [texts[passage.unit_start].text[passage.char_start:]]
    parts += [texts[i].text for i in range(passage.unit_start + 1, passage.unit_end)]
    parts.append(texts[passage.unit_end].text[:passage.char_end])
    return SEGMENT_JOIN.join(parts)


def _windows(text: str, rule: ChunkingRule) -> list[tuple[int, int]]:
    """Tranches de ``max_words`` mots au plus, recouvrement de ``overlap_words`` mots."""
    words = [match.span() for match in re.finditer(r"\S+", text)]
    if not words:
        return []
    if len(words) <= rule.max_words:
        return [(words[0][0], words[-1][1])]
    step = rule.max_words - rule.overlap_words
    spans = []
    for first in range(0, len(words), step):
        last = min(first + rule.max_words, len(words)) - 1
        spans.append((words[first][0], words[last][1]))
        if last == len(words) - 1:
            break
    return spans


def chunk_dossier(dossier: AnonymizedDossier, rule: ChunkingRule) -> list[Passage]:
    passages: list[Passage] = []
    texts = dossier.texts
    index = 0
    while index < len(texts):
        unit = texts[index]
        if unit.section not in rule.sections or not unit.text.strip():
            index += 1
            continue

        if unit.section in TIMESTAMPED and unit.start is not None:
            # Segments horodatés consécutifs de la même vidéo, regroupés jusqu'à max_words.
            last, words = index, len(unit.text.split())
            while (
                last + 1 < len(texts)
                and texts[last + 1].section == unit.section
                and texts[last + 1].start is not None
                and words + len(texts[last + 1].text.split()) <= rule.max_words
            ):
                last += 1
                words += len(texts[last].text.split())
            if last > index or words <= rule.max_words:
                end_unit = texts[last]
                passage = Passage(
                    id=_passage_id(dossier.pseudonym, index, 0, last, len(end_unit.text)),
                    pseudonym=dossier.pseudonym, section=unit.section, label=unit.label,
                    start=unit.start, end=end_unit.end, unit_start=index, unit_end=last,
                    char_start=0, char_end=len(end_unit.text), text="",
                )
                passage.text = passage_text(passage, dossier)
                passages.append(passage)
                index = last + 1
                continue

        for char_start, char_end in _windows(unit.text, rule):
            passages.append(
                Passage(
                    id=_passage_id(dossier.pseudonym, index, char_start, index, char_end),
                    pseudonym=dossier.pseudonym, section=unit.section, label=unit.label, page=unit.page,
                    start=unit.start, end=unit.end, unit_start=index, unit_end=index,
                    char_start=char_start, char_end=char_end, text=unit.text[char_start:char_end],
                )
            )
        index += 1
    return passages
