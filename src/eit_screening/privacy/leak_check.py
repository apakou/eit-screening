"""Contrôle de fuite des dossiers anonymisés, sur la cohorte fictive.

Ce code est volontairement indépendant du module d'anonymisation : il cherche,
dans chaque dossier anonymisé, ce que le ``reference.json`` du dossier fictif
dit être une donnée personnelle (noms, e-mails, téléphones, lien LinkedIn) et
les lieux connus par construction (pays, ville et langue de résidence, lieux
d'études et de travail).

Il relève aussi des **suspects** : dans le texte issu de l'OCR ou de la voix,
les mots qui ressemblent à un nom ou à un lieu sans lui être identiques
(« Lomø » pour « Lomé »). Un suspect n'est pas forcément une fuite ; il est
listé pour qu'un humain le regarde.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field

NOISY_SECTIONS = {"attachment", "personal_statement", "assessment_reflection"}
SUSPECT_THRESHOLD = 75


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def strings(value):
    """Toutes les chaînes d'un JSON relu (clés comprises), pour chercher hors des échappements."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def name_tokens(reference: dict) -> list[str]:
    person = reference["personal"]
    names = [person["first_name"], person["last_name"], person.get("referrer_name")]
    names += [r["full_name"] for r in reference["references"]]
    return [t for name in filter(None, names) for t in re.split(r"[\s-]+", fold(name)) if len(t) >= 2]


def leaks(text: str, reference: dict) -> list[str]:
    """Noms, e-mails, téléphones et liens de ``reference.json`` retrouvés à l'identique dans ``text``."""
    folded = fold(text)
    person = reference["personal"]
    found = [
        token for token in name_tokens(reference)
        if re.search(rf"(?<![^\W\d_]){re.escape(token)}(?![^\W\d_])", folded)
    ]
    emails = [person["email"], person.get("referrer_email"), reference["applicant_email"]]
    emails += [r["email"] for r in reference["references"]]
    found += [e for e in filter(None, emails) if fold(e) in folded]
    digits = re.sub(r"[\s.()+-]", "", folded)
    phones = [person["phone"], person.get("referrer_phone")] + [r["phone"] for r in reference["references"]]
    found += [p for p in filter(None, phones) if re.sub(r"\D", "", p) in digits]
    if person.get("linkedin_url") and fold(person["linkedin_url"]) in folded:
        found.append(person["linkedin_url"])
    return found


def declared_places(reference: dict) -> list[str]:
    """Lieux connus par construction : nationalité, résidence, sa ville et sa langue, lieux d'études et de travail."""
    from ..synthetic import content

    person = reference["personal"]
    places = [person["country_of_citizenship"], person["country_of_residence"], person["interview_city"]]
    places += [e["location"] for e in reference["education"]] + [x["location"] for x in reference["experience"]]
    _, city, language, _ = content.COUNTRIES[person["country_of_residence"]]
    return [p for p in dict.fromkeys(places + [city, language]) if p and p != "Other"]


def without_organisations(text: str, reference: dict) -> str:
    """Texte replié, privé des noms d'établissements et d'employeurs gardés volontairement."""
    folded = fold(text)
    names = [e["institution_other"] or e["institution"] for e in reference["education"]]
    names += [x["organisation"] for x in reference["experience"]]
    for name in filter(None, names):
        folded = folded.replace(fold(name), " ")
    return folded


def place_found(place: str, folded: str) -> bool:
    words = re.findall(r"[^\W_]+", fold(place))
    pattern = r"(?<![^\W\d_])" + r"[\W_]+".join(map(re.escape, words)) + r"(?![^\W\d_])"
    return re.search(pattern, folded) is not None


def suspects(texts: list[dict], reference: dict) -> list[str]:
    """Mots du texte bruité (OCR, voix) proches d'un nom ou d'un lieu sans lui être identiques."""
    from rapidfuzz import fuzz

    targets = [t for t in name_tokens(reference) if len(t) >= 4]
    targets += [w for p in declared_places(reference) for w in re.findall(r"[^\W\d_]+", fold(p)) if len(w) >= 4]
    found = []
    for item in texts:
        if item["section"] not in NOISY_SECTIONS:
            continue
        text = re.sub(r"\[[^\]]*\]", " ", item["text"])  # marques posées par l'anonymisation
        for word in re.findall(r"[^\W\d_]+", fold(text)):
            if len(word) < 4 or word in targets:
                continue
            if any(fuzz.ratio(word, target) >= SUSPECT_THRESHOLD for target in targets):
                found.append(word)
    return sorted(set(found))


class DossierCheck(BaseModel):
    application_id: str
    pseudonym: str
    identity_leaks: list[str] = Field(default_factory=list)
    declared_places: list[str] = Field(default_factory=list)
    suspects: list[str] = Field(default_factory=list)


def check_output(reference: dict, data: dict, filename: str) -> DossierCheck:
    content = "\n".join([filename, *strings(data)])
    text = without_organisations("\n".join(t["text"] for t in data["texts"]), reference)
    return DossierCheck(
        application_id=reference["application_id"],
        pseudonym=data["pseudonym"],
        identity_leaks=leaks(content, reference),
        declared_places=[p for p in declared_places(reference) if place_found(p, text)],
        suspects=suspects(data["texts"], reference),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôle de fuite des dossiers fictifs anonymisés.")
    parser.add_argument("dossiers", type=Path, help="Dossiers fictifs (avec reference.json)")
    parser.add_argument("anonymises", type=Path, help="Dossier de sortie de eit-anonymize")
    parser.add_argument("--table", type=Path, required=True, help="Table de correspondance")
    args = parser.parse_args(argv)

    entries = json.loads(args.table.expanduser().read_text(encoding="utf-8"))["entries"]
    checks = []
    for reference_path in sorted(args.dossiers.rglob("reference.json")):
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        pseudonym = entries.get(reference["application_id"])
        path = args.anonymises / f"{pseudonym}.json"
        if pseudonym is None or not path.exists():
            print(f"{reference['application_id']} : dossier anonymisé introuvable.", file=sys.stderr)
            return 1
        checks.append(check_output(reference, json.loads(path.read_text(encoding="utf-8")), path.name))

    for check in checks:
        if check.identity_leaks or check.declared_places or check.suspects:
            print(
                f"{check.application_id} ({check.pseudonym}) : fuites {check.identity_leaks or '-'} ; "
                f"lieux {check.declared_places or '-'} ; suspects {check.suspects or '-'}"
            )
    total = len(checks)
    print(
        f"\n{total} dossiers contrôlés. Fuites d'identité : {sum(bool(c.identity_leaks) for c in checks)}/{total} ; "
        f"lieu déclaré hors des noms d'établissements : {sum(bool(c.declared_places) for c in checks)}/{total} ; "
        f"dossiers avec un mot suspect dans le texte OCR ou transcrit : {sum(bool(c.suspects) for c in checks)}/{total}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
