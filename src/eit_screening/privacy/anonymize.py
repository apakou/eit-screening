"""Anonymisation du texte destiné au modèle de langage.

Seul du texte anonymisé peut partir vers un modèle hébergé. Ce module construit,
pour chaque dossier, la liste des textes utiles à l'évaluation (réponses libres,
transcriptions, pièces jointes, formation, expériences, noms de fichiers) et y
masque les données personnelles, en quatre couches :

1. **dossier** : les identifiants que le dossier donne lui-même, pour le
   candidat et pour les tiers (parrain, références) : nom complet, chaque mot
   du nom, e-mails, téléphones, liens ;
2. **motifs** : toute autre adresse e-mail, tout numéro de téléphone, tout lien ;
3. **lieux** : pays, villes et nationalités (liste de la configuration et lieux
   déclarés dans le dossier), pour que le modèle ne puisse pas déduire la
   nationalité. Les noms d'établissements et d'employeurs du dossier sont
   gardés tels quels (réglable) ;
4. **reconnaissance d'entités** (Presidio et spaCy) : les noms de personnes et
   les lieux que le dossier ne connaît pas, par exemple un mentor cité dans le CV.

Le texte n'est jamais tiré de ``Application`` en bloc : seuls les champs listés
ici en sortent. Le genre, l'âge et la nationalité restent des métadonnées, à
côté du texte. Le candidat reçoit un pseudonyme aléatoire ; la table de
correspondance est écrite à part, hors du dossier de sortie.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .. import __version__
from ..media.transcribe import Transcript
from ..models import Application
from ..screening.common import git_commit
from ..screening.eligibility import age_on
from ..screening.eligibility import load_config as load_eligibility_config

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


class Labels(BaseModel):
    candidate: str = "[CANDIDAT]"
    person: str = "[PERSONNE_{n}]"
    email: str = "[EMAIL]"
    phone: str = "[TÉLÉPHONE]"
    url: str = "[LIEN]"


class NerRule(BaseModel):
    enabled: bool = True
    language: str = "en"
    model: str = "en_core_web_md"
    min_score: float = 0.6
    allow_list: list[str] = Field(default_factory=list)


class PlaceRule(BaseModel):
    enabled: bool = True
    country_label: str = "[PAYS]"
    city_label: str = "[VILLE]"
    nationality_label: str = "[NATIONALITÉ]"
    place_label: str = "[LIEU]"
    language_label: str = "[LANGUE]"
    keep_organisations: bool = True
    allow_list: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    nationalities: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class NoisyRule(BaseModel):
    """Texte issu de l'OCR ou de la reconnaissance vocale : un nom ou un lieu peut y être mal lu."""

    name_threshold: float = 85
    min_length: int = 4
    place_min_length: int = 5


class TableRule(BaseModel):
    default_path: str


class AnonymizeConfig(BaseModel):
    labels: Labels = Field(default_factory=Labels)
    places: PlaceRule = Field(default_factory=PlaceRule)
    noisy: NoisyRule = Field(default_factory=NoisyRule)
    ner: NerRule = Field(default_factory=NerRule)
    table: TableRule


def load_config(path: Path | str | None = None) -> AnonymizeConfig:
    """Lit la configuration ; sans chemin, prend le fichier livré avec le module."""
    if path is None:
        raw = resources.files(__package__).joinpath("anonymize.toml").read_bytes()
    else:
        raw = Path(path).read_bytes()
    return AnonymizeConfig.model_validate(tomllib.loads(raw.decode("utf-8")))


# --------------------------------------------------------------------------
# Comparaison sans casse ni accents, remplacement dans le texte d'origine
# --------------------------------------------------------------------------


def _fold(text: str) -> tuple[str, list[int]]:
    """Texte sans accents ni casse, avec la position d'origine de chaque caractère."""
    folded: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        base = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
        for part in base.casefold():
            folded.append(part)
            origin.append(index)
    return "".join(folded), origin


def _fold_plain(text: str) -> str:
    return _fold(text)[0]


# Un mot de nom est borné par tout ce qui n'est pas une lettre : « Temi_Eze_CV »,
# « temi-eze82 » ou « Temi, » laissent tous voir « temi ».
_NOT_LETTER_BEFORE = r"(?<![^\W\d_])"
_NOT_LETTER_AFTER = r"(?![^\W\d_])"
_NAME_SEPARATOR = r"[\s._,-]+"

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
# Au moins 9 chiffres, séparés au plus par un caractère : « 2021 - 2024 » n'en est pas un.
PHONE_PATTERN = re.compile(r"(?<![\w+])\+?\d(?:[\s.()-]?\d){8,14}(?!\w)")

Kind = Literal["candidate", "person", "email", "phone", "url", "country", "city", "nationality", "language", "place", "keep"]
Layer = Literal["dossier", "approx", "pattern", "place", "ner"]


@dataclass
class _Rule:
    """Motif cherché sur le texte replié (sans accents ni casse)."""

    pattern: re.Pattern
    kind: Kind
    label: str | None  # None : passage protégé, laissé tel quel


@dataclass
class _Span:
    start: int
    end: int
    kind: Kind
    label: str | None


def _apply(text: str, rules: list[_Rule]) -> tuple[str, list[tuple[Kind, str]]]:
    """Remplace dans ``text`` les passages trouvés par ``rules`` ; renvoie le texte et ce qui a été masqué."""
    folded, origin = _fold(text)
    spans: list[_Span] = []
    for rule in rules:
        for match in rule.pattern.finditer(folded):
            if match.end() > match.start():
                start, end = origin[match.start()], origin[match.end() - 1] + 1
                spans.append(_Span(start, end, rule.kind, rule.label))
    # Les passages les plus longs d'abord ; un passage qui en chevauche un autre est ignoré.
    spans.sort(key=lambda s: (-(s.end - s.start), s.start))
    kept: list[_Span] = []
    for span in spans:
        if all(span.end <= other.start or span.start >= other.end for other in kept):
            kept.append(span)
    masked: list[tuple[Kind, str]] = []
    for span in sorted(kept, key=lambda s: s.start, reverse=True):
        if span.label is None:
            continue
        masked.append((span.kind, text[span.start:span.end]))
        text = text[:span.start] + span.label + text[span.end:]
    masked.reverse()
    return text, masked


# --------------------------------------------------------------------------
# Identités connues par le dossier
# --------------------------------------------------------------------------


@dataclass
class Identity:
    """Personne citée par le dossier : le candidat ou un tiers."""

    kind: Literal["candidate", "person"]
    label: str
    names: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


def _clean(values) -> list[str]:
    return [v.strip() for v in values if v and v.strip()]


def identities(app: Application, labels: Labels) -> list[Identity]:
    """Candidat, parrain et références, dans cet ordre (le candidat est prioritaire)."""
    person = app.personal
    candidate = Identity(
        kind="candidate",
        label=labels.candidate,
        names=_clean([" ".join(_clean([person.first_name, person.last_name])), app.applicant_display_name]),
        emails=_clean([person.email, app.applicant_email]),
        phones=_clean([person.phone]),
        urls=_clean([person.linkedin_url, *app.evidence_urls, *(u.url for u in app.uploads)]),
    )
    others: list[Identity] = []
    third_parties = [(person.referrer_name, person.referrer_email, person.referrer_phone)]
    third_parties += [(r.full_name, r.email, r.phone) for r in app.references]
    for name, email, phone in third_parties:
        if not (name or email or phone):
            continue
        others.append(
            Identity(
                kind="person",
                label=labels.person.format(n=len(others) + 1),
                names=_clean([name]),
                emails=_clean([email]),
                phones=_clean([phone]),
            )
        )
    return [candidate, *others]


def _name_tokens(name: str) -> list[str]:
    return [token for token in re.split(r"[\s-]+", _fold_plain(name)) if len(token) >= 2]


def _phone_rule(phone: str, kind: Kind, label: str) -> _Rule | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        return None
    return _Rule(re.compile(r"\+?" + r"[\s.()-]?".join(digits)), kind, label)


def _dossier_rules(people: list[Identity], labels: Labels) -> list[_Rule]:
    """Motifs tirés des identités du dossier : liens et e-mails, téléphones, puis noms."""
    rules: list[_Rule] = []
    for identity in people:
        for url in identity.urls:
            rules.append(_Rule(re.compile(re.escape(_fold_plain(url))), "url", labels.url))
        for email in identity.emails:
            rules.append(_Rule(re.compile(re.escape(_fold_plain(email))), "email", labels.email))
        for phone in identity.phones:
            rule = _phone_rule(phone, "phone", labels.phone)
            if rule:
                rules.append(rule)
    seen: set[str] = set()
    for identity in people:  # le candidat en premier : un mot partagé lui revient
        for name in identity.names:
            tokens = _name_tokens(name)
            if len(tokens) >= 2:
                for order in (tokens, list(reversed(tokens))):
                    body = _NAME_SEPARATOR.join(re.escape(t) for t in order)
                    rules.append(_Rule(re.compile(_NOT_LETTER_BEFORE + body + _NOT_LETTER_AFTER), identity.kind, identity.label))
            for token in tokens:
                if token in seen:
                    continue
                seen.add(token)
                pattern = re.compile(_NOT_LETTER_BEFORE + re.escape(token) + _NOT_LETTER_AFTER)
                rules.append(_Rule(pattern, identity.kind, identity.label))
    return rules


def _phrase_pattern(phrase: str, plural: bool = False) -> re.Pattern | None:
    """Expression en mots entiers, quels que soient les séparateurs (« Côte d’Ivoire », « Porto Novo »)."""
    words = re.findall(r"[^\W_]+", _fold_plain(phrase))
    if not words:
        return None
    body = r"[\W_]+".join(re.escape(w) for w in words) + ("s?" if plural else "")
    return re.compile(_NOT_LETTER_BEFORE + body + _NOT_LETTER_AFTER)


def organisations(app: Application) -> list[str]:
    """Établissements et employeurs déclarés dans le dossier."""
    names = []
    for edu in app.education:
        names += [edu.institution, edu.institution_other]
    names += [exp.organisation for exp in app.experience]
    return [n for n in _clean(names) if n.casefold() != "other"]


def _place_rules(app: Application, rule: PlaceRule) -> list[_Rule]:
    """Pays, villes, nationalités et langues locales : configuration et lieux déclarés dans le dossier."""
    person = app.personal
    countries = list(rule.countries) + _clean(
        [person.country_of_residence, person.country_of_citizenship]
        + [e.location for e in app.education] + [x.location for x in app.experience]
    )
    cities = list(rule.cities) + _clean([person.interview_city])
    rules: list[_Rule] = []
    if rule.keep_organisations:
        for name in organisations(app):
            pattern = _phrase_pattern(name)
            if pattern:
                rules.append(_Rule(pattern, "keep", None))
    for values, kind, label, plural in (
        (countries, "country", rule.country_label, False),
        (cities, "city", rule.city_label, False),
        (rule.nationalities, "nationality", rule.nationality_label, True),
        (rule.languages, "language", rule.language_label, False),
    ):
        for value in dict.fromkeys(v for v in values if v.casefold() != "other"):
            pattern = _phrase_pattern(value, plural)
            if pattern:
                rules.append(_Rule(pattern, kind, label))
    return rules


def _pattern_rules(labels: Labels) -> list[_Rule]:
    return [
        _Rule(URL_PATTERN, "url", labels.url),
        _Rule(EMAIL_PATTERN, "email", labels.email),
        _Rule(PHONE_PATTERN, "phone", labels.phone),
    ]


# --------------------------------------------------------------------------
# Reconnaissance d'entités
# --------------------------------------------------------------------------


@cache
def _analyzer(model: str, language: str):
    """Moteur Presidio, chargé une seule fois par modèle."""
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": language, "model_name": model}]}
    )
    return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=[language])


# --------------------------------------------------------------------------
# Masquage
# --------------------------------------------------------------------------


def _known_non_persons(app: Application) -> list[str]:
    """Lieux, organisations, postes et formations que le dossier nomme lui-même (forme repliée)."""
    values = [app.personal.country_of_citizenship, app.personal.country_of_residence, app.personal.based_in]
    values += [app.personal.interview_city]
    for edu in app.education:
        values += [edu.degree, edu.major, edu.institution, edu.institution_other, edu.location, edu.other_training]
    for exp in app.experience:
        values += [exp.organisation, exp.job_title, exp.location]
    values += load_eligibility_config().citizenship.countries
    folded = {" ".join(re.findall(r"[^\W\d_]+", _fold_plain(v))) for v in values if v}
    return sorted(v for v in folded if v)


def _noisy_place_tokens(app: Application, rule: PlaceRule) -> list[tuple[str, Kind, str]]:
    """Pays et villes d'un seul mot, comparés par ressemblance dans le texte issu de l'OCR ou de la voix.

    Nationalités et langues en sont exclues : trop proches de mots courants
    (« librarian » et « Liberian », « server » et « Serer »).
    """
    person = app.personal
    declared = _clean([person.country_of_residence, person.country_of_citizenship, person.interview_city]
                      + [e.location for e in app.education] + [x.location for x in app.experience])
    tokens: dict[str, tuple[Kind, str]] = {}
    for values, kind, label in (
        (rule.countries + declared, "country", rule.country_label),
        (rule.cities, "city", rule.city_label),
    ):
        for value in values:
            words = re.findall(r"[^\W\d_]+", _fold_plain(value))
            if len(words) == 1 and words[0] != "other":
                tokens.setdefault(words[0], (kind, label))
    return [(word, kind, label) for word, (kind, label) in tokens.items()]


class Masker:
    """Masque les données personnelles d'un dossier dans n'importe quel texte.

    Les tiers repérés par la reconnaissance d'entités gardent le même numéro
    d'un texte à l'autre du même dossier.
    """

    def __init__(self, app: Application, config: AnonymizeConfig) -> None:
        self.config = config
        labels = config.labels
        self.people = identities(app, labels)
        self._dossier_rules = _dossier_rules(self.people, labels)
        self._pattern_rules = _pattern_rules(labels)
        places = config.places
        self._place_rules = _place_rules(app, places) if places.enabled else []
        self._place_allow = {" ".join(re.findall(r"[^\W\d_]+", _fold_plain(w))) for w in places.allow_list}
        self._organisations = [
            " ".join(re.findall(r"[^\W\d_]+", _fold_plain(name))) for name in organisations(app)
        ] if places.keep_organisations else []
        self._ner_labels: dict[str, str] = {}
        self._next_person = sum(1 for p in self.people if p.kind == "person") + 1
        self._allow = {_fold_plain(word) for word in config.ner.allow_list}
        self._not_person = _known_non_persons(app)
        self._noisy_tokens = [
            (token, identity.kind, identity.label)
            for identity in self.people
            for name in identity.names
            for token in _name_tokens(name)
            if len(token) >= config.noisy.min_length
        ]
        self._noisy_places = _noisy_place_tokens(app, places) if places.enabled else []
        self.approx_strings: list[str] = []  # mots masqués par ressemblance (OCR, transcription)
        self.counts: dict[str, int] = {}
        self.ner_strings: list[str] = []  # noms masqués par la seule reconnaissance d'entités
        self.ner_places: list[str] = []  # lieux masqués par la seule reconnaissance d'entités

    def _count(self, layer: Layer, masked: list[tuple[Kind, str]]) -> None:
        for kind, _ in masked:
            key = f"{layer}:{kind}"
            self.counts[key] = self.counts.get(key, 0) + 1

    def _is_person(self, found: str) -> bool:
        """Écarte ce que le dossier désigne déjà comme lieu, organisation, poste ou formation."""
        if "[" in found or "]" in found or not any(char.isupper() for char in found):
            return False
        key = " ".join(re.findall(r"[^\W\d_]+", _fold_plain(found)))
        if len(key) < 2 or key in self._allow or set(key.split()) & self._allow:
            return False
        # Mots entiers : « ben » n'est pas écarté parce que « benin » est un pays.
        pattern = re.compile(r"(?<!\S)" + re.escape(key) + r"(?!\S)")
        return not any(pattern.search(known) for known in self._not_person)

    def _is_place(self, found: str) -> bool:
        """Lieu à masquer : ni marque déjà posée, ni région sans lien avec la nationalité, ni nom d'employeur."""
        if re.search(r"[\[\]\d_]", found) or not any(char.isupper() for char in found):
            return False
        key = " ".join(re.findall(r"[^\W\d_]+", _fold_plain(found)))
        if len(key) < 2 or key in self._place_allow or set(key.split()) & self._allow:
            return False
        pattern = re.compile(r"(?<!\S)" + re.escape(key) + r"(?!\S)")
        return not any(pattern.search(name) for name in self._organisations)

    def _ner(self, text: str) -> str:
        rule = self.config.ner
        analyzer = _analyzer(rule.model, rule.language)
        entities = ["PERSON", "LOCATION"] if self.config.places.enabled else ["PERSON"]
        spans = []
        offset = 0
        # Ligne par ligne : une entité ne déborde pas d'une ligne du CV sur la suivante.
        for line in text.split("\n"):
            results = analyzer.analyze(text=line, language=rule.language, entities=entities) if line.strip() else []
            for result in results:
                found = line[result.start:result.end]
                if result.score < rule.min_score:
                    continue
                if result.entity_type == "PERSON" and self._is_person(found):
                    key = _fold_plain(found).strip()
                    if key not in self._ner_labels:
                        self._ner_labels[key] = self.config.labels.person.format(n=self._next_person)
                        self._next_person += 1
                    spans.append((offset + result.start, offset + result.end, "person", self._ner_labels[key], found))
                elif result.entity_type == "LOCATION" and self._is_place(found):
                    label = self.config.places.place_label
                    spans.append((offset + result.start, offset + result.end, "place", label, found))
            offset += len(line) + 1
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        kept, last_end = [], -1
        for span in spans:
            if span[0] >= last_end:
                kept.append(span)
                last_end = span[1]
        for start, end, kind, label, found in reversed(kept):
            text = text[:start] + label + text[end:]
            (self.ner_strings if kind == "person" else self.ner_places).append(found)
        self._count("ner", [(kind, found) for _, _, kind, _, found in kept])
        return text

    def _approximate(
        self, text: str, tokens: list[tuple[str, Kind, str]], min_length: int, skip_exact: bool = False
    ) -> str:
        """Masque les mots proches d'un mot connu (« Mensa » pour « Mensah »).

        ``skip_exact`` : un mot identique est laissé tel quel ; pour les lieux, il a
        déjà été masqué par la couche exacte, ou protégé dans un nom d'établissement.
        """
        from rapidfuzz import fuzz

        threshold = self.config.noisy.name_threshold
        pieces, last, masked = [], 0, []
        for match in re.finditer(r"[^\W\d_]+", text):
            word = match.group(0)
            inside_label = text[max(0, match.start() - 1):match.start()] == "["  # « [CANDIDAT] », « [PERSONNE_1] »
            if inside_label or len(word) < min_length:
                continue
            folded = _fold_plain(word)
            best = max(((fuzz.ratio(folded, token), kind, label) for token, kind, label in tokens), default=None)
            if best is None or best[0] < threshold or (skip_exact and best[0] >= 100):
                continue
            pieces.append(text[last:match.start()] + best[2])
            last = match.end()
            masked.append((best[1], word))
            self.approx_strings.append(word)
        pieces.append(text[last:])
        self._count("approx", masked)
        return "".join(pieces)

    def mask(self, text: str | None, noisy: bool = False) -> str:
        """Texte sans les données personnelles connues ou repérées.

        ``noisy`` : texte issu de l'OCR ou de la reconnaissance vocale. Les mots
        proches d'un nom du dossier y sont aussi masqués, car un nom mal lu
        échappe à la comparaison exacte.
        """
        if not text:
            return text or ""
        text, masked = _apply(text, self._dossier_rules)
        self._count("dossier", masked)
        if noisy:
            text = self._approximate(text, self._noisy_tokens, self.config.noisy.min_length)
        text, masked = _apply(text, self._pattern_rules)
        self._count("pattern", masked)
        if self._place_rules:
            text, masked = _apply(text, self._place_rules)
            self._count("place", masked)
            if noisy:
                text = self._approximate(
                    text, self._noisy_places, self.config.noisy.place_min_length, skip_exact=True
                )
        if self.config.ner.enabled:
            text = self._ner(text)
        return text


# --------------------------------------------------------------------------
# Dossier anonymisé
# --------------------------------------------------------------------------


class Metadata(BaseModel):
    """Données gardées à côté du texte, jamais dedans."""

    gender: str | None = None
    age: int | None = None
    citizenship: str | None = None


class AnonymizedText(BaseModel):
    section: Literal[
        "essay", "personal_statement", "assessment_reflection", "attachment", "education", "experience", "uploads"
    ]
    label: str | None = None
    page: int | None = None
    # Horodatage d'un segment de transcription, en secondes (None si inconnu).
    start: float | None = None
    end: float | None = None
    text: str


class AnonymizedDossier(BaseModel):
    pseudonym: str
    metadata: Metadata
    texts: list[AnonymizedText]
    replacements: dict[str, int] = Field(default_factory=dict)


def _education_text(app: Application) -> list[str]:
    lines = []
    for edu in app.education:
        parts = [edu.degree, edu.major, edu.institution_other or edu.institution, edu.location]
        line = ", ".join(p for p in parts if p)
        if edu.graduation_date:
            line += f" ({edu.graduation_date.year})"
        if edu.other_training:
            line += f". Autre formation : {edu.other_training}"
        lines.append(line)
    return lines


def _experience_text(app: Application) -> list[str]:
    lines = []
    for exp in app.experience:
        parts = [exp.job_title, exp.organisation, exp.location]
        line = ", ".join(p for p in parts if p)
        start = exp.start_date.strftime("%m/%Y") if exp.start_date else "?"
        end = "en cours" if exp.current else (exp.end_date.strftime("%m/%Y") if exp.end_date else "?")
        lines.append(f"{line} ({start} - {end})")
    return lines


def anonymize_dossier(
    app: Application,
    pseudonym: str,
    transcripts: dict[str, str | Transcript] | None = None,
    config: AnonymizeConfig | None = None,
) -> tuple[AnonymizedDossier, Masker]:
    """Construit le dossier anonymisé. Le ``Masker`` renvoyé garde les détails, à ne pas exporter.

    Une transcription horodatée donne un texte par segment, avec son début et
    sa fin. Le texte issu de l'OCR ou de la reconnaissance vocale est masqué
    avec la couche approchée (noms mal lus).
    """
    config = config or load_config()
    masker = Masker(app, config)
    texts: list[AnonymizedText] = []

    for essay in app.essays:
        texts.append(AnonymizedText(section="essay", label=essay.question, text=masker.mask(essay.answer)))
    for section in ("personal_statement", "assessment_reflection"):
        transcript = (transcripts or {}).get(section)
        if isinstance(transcript, str):
            if transcript.strip():
                texts.append(AnonymizedText(section=section, text=masker.mask(transcript.strip())))
        elif transcript is not None:
            noisy = transcript.source == "faster-whisper"
            if any(segment.start is not None for segment in transcript.segments):
                for segment in transcript.segments:
                    texts.append(
                        AnonymizedText(
                            section=section, start=segment.start, end=segment.end,
                            text=masker.mask(segment.text, noisy=noisy),
                        )
                    )
            elif transcript.text:
                texts.append(AnonymizedText(section=section, text=masker.mask(transcript.text, noisy=noisy)))
    for page in app.attachment_pages:
        if page.text.strip():
            text = masker.mask(page.text, noisy=page.text_source == "ocr")
            texts.append(AnonymizedText(section="attachment", page=page.page_number, text=text))
    for line in _education_text(app):
        texts.append(AnonymizedText(section="education", text=masker.mask(line)))
    for line in _experience_text(app):
        texts.append(AnonymizedText(section="experience", text=masker.mask(line)))
    uploads = [f"{u.label} : {u.link_text}" for u in app.uploads]
    if uploads:
        texts.append(AnonymizedText(section="uploads", text=masker.mask("\n".join(uploads))))

    person = app.personal
    reference_date = load_eligibility_config().age.reference_date
    metadata = Metadata(
        gender=person.gender,
        age=age_on(person.date_of_birth, reference_date) if person.date_of_birth else None,
        citizenship=person.country_of_citizenship,
    )
    dossier = AnonymizedDossier(
        pseudonym=pseudonym, metadata=metadata, texts=texts, replacements=dict(sorted(masker.counts.items()))
    )
    return dossier, masker


# --------------------------------------------------------------------------
# Table de correspondance
# --------------------------------------------------------------------------


class PseudonymTable:
    """Correspondance numéro de dossier -> pseudonyme, dans un fichier à part.

    Un pseudonyme est tiré au hasard (module ``secrets``) la première fois
    qu'un dossier est vu, puis réutilisé : relancer l'anonymisation ne change
    pas les pseudonymes.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()
        self.entries: dict[str, str] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = dict(data.get("entries", {}))

    def pseudonym(self, application_id: str) -> str:
        if application_id not in self.entries:
            used = set(self.entries.values())
            while True:
                candidate = f"C-{secrets.token_hex(4).upper()}"
                if candidate not in used:
                    break
            self.entries[application_id] = candidate
        return self.entries[application_id]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"note": "Table de correspondance : ne pas versionner, ne pas partager.", "entries": self.entries}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------------

def residual_places(app: Application, dossier: AnonymizedDossier) -> tuple[list[str], list[str]]:
    """Lieux déclarés dans le dossier encore lisibles dans le texte anonymisé.

    Renvoie ceux qui restent hors des noms d'établissements et d'employeurs, puis
    ceux qui ne restent qu'à l'intérieur de ces noms (gardés volontairement).
    """
    person = app.personal
    declared = _clean(
        [person.country_of_citizenship, person.country_of_residence, person.interview_city]
        + [e.location for e in app.education] + [x.location for x in app.experience]
    )
    text = _fold_plain("\n".join(t.text for t in dossier.texts))
    without_orgs = text
    for name in organisations(app):
        pattern = _phrase_pattern(name)
        if pattern:
            without_orgs = pattern.sub(" ", without_orgs)
    free, in_orgs = [], []
    for place in dict.fromkeys(p for p in declared if p.casefold() != "other"):
        pattern = _phrase_pattern(place)
        if pattern is None:
            continue
        if pattern.search(without_orgs):
            free.append(place)
        elif pattern.search(text):
            in_orgs.append(place)
    return free, in_orgs


TRANSCRIPT_FILES = {
    "personal_statement": "personal_statement.txt",
    "assessment_reflection": "assessment_reflection.txt",
}


def read_transcripts(folder: Path) -> dict[str, str]:
    """Transcriptions posées à côté du PDF (dossiers fictifs ; plus tard, sortie de la transcription)."""
    found = {}
    for section, name in TRANSCRIPT_FILES.items():
        path = folder / name
        if path.exists():
            found[section] = path.read_text(encoding="utf-8")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Anonymise les dossiers PDF : texte sans données personnelles, pseudonyme aléatoire."
    )
    parser.add_argument("dossiers", type=Path, help="Dossier parcouru récursivement à la recherche de application.pdf")
    parser.add_argument("-o", "--out", type=Path, required=True, help="Dossier de sortie des dossiers anonymisés")
    parser.add_argument("--table", type=Path, help="Table de correspondance (défaut : voir anonymize.toml)")
    parser.add_argument("--config", type=Path, help="Fichier de paramètres TOML")
    parser.add_argument(
        "--details", action="store_true", help="Affiche les noms masqués par la seule reconnaissance d'entités"
    )
    args = parser.parse_args(argv)

    from ..ingestion.smapply_pdf import parse_application
    from ..media.extract import load_extraction

    config = load_config(args.config)
    table_path = (args.table or Path(config.table.default_path)).expanduser()
    if _is_inside(table_path, args.out):
        print("La table de correspondance ne doit pas être dans le dossier de sortie.", file=sys.stderr)
        return 1
    paths = sorted(args.dossiers.rglob("application.pdf"))
    if not paths:
        print(f"Aucun fichier application.pdf trouvé dans {args.dossiers}.", file=sys.stderr)
        return 1

    table = PseudonymTable(table_path)
    args.out.mkdir(parents=True, exist_ok=True)
    groups = {
        "candidat": ("candidate",),
        "tiers": ("person",),
        "contact": ("email", "phone", "url"),
        "lieux": ("country", "city", "nationality", "language", "place"),
    }
    print(f"{'Pseudonyme':<12} {'Textes':>6}  " + " ".join(f"{g:>8}" for g in groups) + f"  {'dont NER':>8}  Lieu déclaré resté")
    totals: dict[str, int] = {}
    used_extraction = 0
    outside, only_in_organisations = 0, 0
    ner_details: list[tuple[str, list[str], list[str], list[str]]] = []
    for path in paths:
        app = parse_application(path)
        pseudonym = table.pseudonym(app.application_id)
        extraction = load_extraction(path.parent)
        if extraction is not None:
            # Pièces jointes relues par Docling (OCR compris) et transcriptions horodatées.
            app = app.model_copy(update={"attachment_pages": extraction.attachment_pages})
            transcripts = dict(extraction.transcripts)
            used_extraction += 1
        else:
            transcripts = read_transcripts(path.parent)
        dossier, masker = anonymize_dossier(app, pseudonym, transcripts, config)
        (args.out / f"{pseudonym}.json").write_text(dossier.model_dump_json(indent=2), encoding="utf-8")

        counts = {
            group: sum(v for key, v in dossier.replacements.items() if key.split(":")[1] in kinds)
            for group, kinds in groups.items()
        }
        ner = sum(v for key, v in dossier.replacements.items() if key.startswith("ner:"))
        for key, value in dossier.replacements.items():
            totals[key] = totals.get(key, 0) + value
        free, in_orgs = residual_places(app, dossier)
        outside += bool(free)
        only_in_organisations += bool(in_orgs) and not free
        state = "oui" if free else ("dans un nom d'établissement" if in_orgs else "non")
        if masker.ner_strings or masker.ner_places or masker.approx_strings:
            ner_details.append((
                pseudonym, sorted(set(masker.ner_strings)), sorted(set(masker.ner_places)),
                sorted(set(masker.approx_strings)),
            ))
        print(
            f"{pseudonym:<12} {len(dossier.texts):>6}  " + " ".join(f"{counts[g]:>8}" for g in groups)
            + f"  {ner:>8}  {state}"
        )
    table.save()

    print(f"\n{len(paths)} dossiers anonymisés dans {args.out} ; table de correspondance : {table_path}.")
    print(f"Dossiers lus avec extraction.json (OCR, transcriptions) : {used_extraction}/{len(paths)}.")
    print("Remplacements par couche et par type : " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())))
    print(
        "Lieux déclarés dans le dossier (nationalité, résidence, lieux d'études et de travail, ville d'entretien) "
        f"encore lisibles : {outside}/{len(paths)} dossiers dans le texte libre, "
        f"{only_in_organisations}/{len(paths)} seulement dans un nom d'établissement ou d'employeur gardé."
    )
    if args.details:
        for pseudonym, names, places, approx in ner_details:
            print(f"  {pseudonym} : NER personnes {names or '-'} ; NER lieux {places or '-'} ; ressemblance {approx or '-'}")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_commit": git_commit(),
        "ner_model": config.ner.model if config.ner.enabled else None,
        "dossiers": len(paths),
        "replacements": dict(sorted(totals.items())),
        "dossiers_with_declared_place_in_free_text": outside,
        "dossiers_with_declared_place_only_in_kept_organisations": only_in_organisations,
    }
    (args.out / "_resume.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
