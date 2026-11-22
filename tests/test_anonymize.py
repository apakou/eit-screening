"""Anonymisation : test de fuite sur la cohorte, couches de masquage, pseudonymes."""

import json
import re
import stat

import pytest

from eit_screening.models import Application, Education, Essay, Personal, Reference, WorkExperience
from eit_screening.privacy.leak_check import (
    declared_places,
    leaks,
    place_found,
    strings,
    without_organisations,
)
from eit_screening.privacy.anonymize import (
    PseudonymTable,
    anonymize_dossier,
    load_config,
    main,
    read_transcripts,
)

CONFIG = load_config()

# --------------------------------------------------------------------------
# Cohorte de référence anonymisée une fois pour tout le module
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def anonymized(cohort, parsed, tmp_path_factory):
    out_dir, dossiers = cohort
    target = tmp_path_factory.mktemp("anonymises")
    table = PseudonymTable(tmp_path_factory.mktemp("secret") / "table.json")
    for dossier in dossiers:
        app_id = dossier.application.application_id
        pseudonym = table.pseudonym(app_id)
        result, _ = anonymize_dossier(
            parsed[app_id], pseudonym, read_transcripts(out_dir / "dossiers" / app_id), CONFIG
        )
        (target / f"{pseudonym}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    table.save()
    return target, table


def test_no_leak_in_reference_cohort(cohort, anonymized):
    """Critère d'acceptation : aucun nom, e-mail ni téléphone de reference.json dans la sortie."""
    out_dir, dossiers = cohort
    target, table = anonymized
    assert len(list(target.glob("*.json"))) == 40
    for dossier in dossiers:
        app_id = dossier.application.application_id
        reference = json.loads((out_dir / "dossiers" / app_id / "reference.json").read_text(encoding="utf-8"))
        path = target / f"{table.entries[app_id]}.json"
        content = "\n".join([path.name, *strings(json.loads(path.read_text(encoding="utf-8")))])
        assert leaks(content, reference) == [], app_id
        assert app_id not in content


def test_detector_finds_leaks_in_raw_dossiers(cohort, parsed):
    """Le détecteur a des dents : sans anonymisation, il trouve une fuite dans chaque dossier."""
    out_dir, dossiers = cohort
    for dossier in dossiers:
        app_id = dossier.application.application_id
        app = parsed[app_id]
        reference = json.loads((out_dir / "dossiers" / app_id / "reference.json").read_text(encoding="utf-8"))
        raw = [e.answer or "" for e in app.essays] + [p.text for p in app.attachment_pages]
        raw += list(read_transcripts(out_dir / "dossiers" / app_id).values())
        raw += [u.link_text for u in app.uploads]
        assert leaks("\n".join(raw), reference), app_id


def test_output_shape(anonymized):
    target, _ = anonymized
    for path in target.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == data["pseudonym"]
        assert set(data) == {"pseudonym", "metadata", "texts", "replacements"}
        assert set(data["metadata"]) == {"gender", "age", "citizenship"}
        text = "\n".join(t["text"] for t in data["texts"])
        assert "@" not in text
        assert not re.search(r"\d{9,}", text)
        assert "http" not in text and "www." not in text


def test_nothing_masked_by_ner_alone_on_cohort(anonymized):
    """Sur la cohorte fictive, ni tiers ni lieu inconnus : la reconnaissance d'entités ne doit rien masquer."""
    target, _ = anonymized
    for path in target.glob("*.json"):
        replacements = json.loads(path.read_text(encoding="utf-8"))["replacements"]
        assert not [key for key in replacements if key.startswith("ner:")], path.name


def test_no_declared_place_outside_kept_organisations(cohort, anonymized):
    """Pays, ville et langue du candidat ne restent que dans les noms d'établissements gardés."""
    out_dir, dossiers = cohort
    target, table = anonymized
    for dossier in dossiers:
        app_id = dossier.application.application_id
        reference = json.loads((out_dir / "dossiers" / app_id / "reference.json").read_text(encoding="utf-8"))
        data = json.loads((target / f"{table.entries[app_id]}.json").read_text(encoding="utf-8"))
        text = without_organisations("\n".join(t["text"] for t in data["texts"]), reference)
        assert [p for p in declared_places(reference) if place_found(p, text)] == [], app_id


def test_raw_dossiers_name_their_places(cohort, parsed):
    """Le contrôle précédent a des dents : les dossiers bruts nomment leurs lieux hors des noms d'établissements.

    Pas tous : un dossier faible sans CV peut ne citer aucun lieu (EIT-2027-001005 dans la
    cohorte de référence). Le contrôle doit en trouver dans la très grande majorité.
    """
    out_dir, dossiers = cohort
    silent = []
    for dossier in dossiers:
        app_id = dossier.application.application_id
        app = parsed[app_id]
        reference = json.loads((out_dir / "dossiers" / app_id / "reference.json").read_text(encoding="utf-8"))
        raw = [e.answer or "" for e in app.essays] + [p.text for p in app.attachment_pages]
        raw += list(read_transcripts(out_dir / "dossiers" / app_id).values())
        text = without_organisations("\n".join(raw), reference)
        if not any(place_found(p, text) for p in declared_places(reference)):
            silent.append(app_id)
    assert len(silent) <= 2, silent


# --------------------------------------------------------------------------
# Couches de masquage, sur des dossiers construits à la main
# --------------------------------------------------------------------------


def _app(essays, **personal):
    person = {"first_name": "Temi", "last_name": "Eze", "email": "temi.eze82@example.org", "phone": "+234000139060"}
    person.update(personal)
    return Application(
        application_id="0000009999",
        personal=Personal(**person),
        essays=[Essay(question=f"Q{i}", answer=answer) for i, answer in enumerate(essays)],
        references=[Reference(kind="academic", full_name="Kwame Boateng", email="k.b@example.org", phone="+233000111222")],
    )


def _texts(app, config=CONFIG):
    result, masker = anonymize_dossier(app, "C-TEST", config=config)
    return [t.text for t in result.texts], result, masker


def test_names_in_file_names_and_links():
    texts, _, _ = _texts(_app(["Temi_Eze_CV.pdf, temi-eze82 and TEMI EZE, then Eze, Temi."]))
    assert texts[0] == "[CANDIDAT]_CV.pdf, [CANDIDAT]82 and [CANDIDAT], then [CANDIDAT]."


def test_short_names_do_not_eat_words():
    texts, _, _ = _texts(_app(["Esi likes design and Esian food."], first_name="Esi", last_name="Owusu"))
    assert texts[0] == "[CANDIDAT] likes design and Esian food."


def test_accents_are_ignored_but_text_is_kept():
    texts, _, _ = _texts(_app(["Kouame Kone wrote to Kouamé Koné, à Abidjan."], first_name="Kouamé", last_name="Koné"))
    assert texts[0] == "[CANDIDAT] wrote to [CANDIDAT], à [VILLE]."


def test_third_parties_known_by_the_dossier():
    texts, result, _ = _texts(_app(["My lecturer Kwame Boateng (k.b@example.org, +233 000 111 222) helped."]))
    assert texts[0] == "My lecturer [PERSONNE_1] ([EMAIL], [TÉLÉPHONE]) helped."
    assert result.replacements["dossier:person"] == 1


def test_unknown_identifiers_by_pattern():
    texts, result, _ = _texts(
        _app(["Write to someone@example.com, call +221 77 000 12 34 or see https://example.org/x. Worked 2021 - 2024."])
    )
    assert texts[0] == "Write to [EMAIL], call [TÉLÉPHONE] or see [LIEN] Worked 2021 - 2024."
    assert {key for key in result.replacements} == {"pattern:email", "pattern:phone", "pattern:url"}


def test_over_masking_is_accepted():
    # « Kwame » est aussi le nom d'un tiers : il est masqué même dans le nom de l'université.
    texts, _, _ = _texts(_app(["I studied at Kwame Nkrumah University."]))
    assert texts[0] == "I studied at [PERSONNE_1] Nkrumah University."


def test_ner_masks_unknown_people_consistently():
    app = _app([
        "I found a mentor, Adaeze Nwosu, who introduced me to John Smith.",
        "Adaeze Nwosu still reviews my Django code.",
    ])
    texts, result, masker = _texts(app)
    assert texts[0] == "I found a mentor, [PERSONNE_2], who introduced me to [PERSONNE_3]."
    assert texts[1] == "[PERSONNE_2] still reviews my Django code."
    assert result.replacements["ner:person"] == 3
    assert sorted(set(masker.ner_strings)) == ["Adaeze Nwosu", "John Smith"]


def test_ner_can_be_disabled():
    config = CONFIG.model_copy(deep=True)
    config.ner.enabled = False
    texts, result, _ = _texts(_app(["I found a mentor, Adaeze Nwosu."]), config)
    assert texts[0] == "I found a mentor, Adaeze Nwosu."
    assert "ner:person" not in result.replacements


def test_ner_skips_what_the_dossier_names_as_organisation():
    app = _app(["I worked at Nimba Cloud in Sierra Leone."])
    app.experience = [WorkExperience(organisation="Nimba Cloud", location="Sierra Leone")]
    texts, _, _ = _texts(app)
    assert texts[0] == "I worked at Nimba Cloud in [PAYS]."


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("My manager Ben reviewed my code.", "My manager [PERSONNE_2] reviewed my code."),
        ("I met Ali at the hackathon.", "I met [PERSONNE_2] at the hackathon."),
    ],
)
def test_ner_word_level_filter(sentence, expected):
    # « Ben » est dans « Benin », « Ali » dans « Mali » : seuls des mots entiers écartent un nom.
    app = _app([sentence], country_of_citizenship="Benin", country_of_residence="Mali")
    texts, _, _ = _texts(app)
    assert texts[0] == expected


# --------------------------------------------------------------------------
# Lieux
# --------------------------------------------------------------------------


def _with_education(essay, institution="Université de Lomé"):
    app = _app([essay])
    app.education = [Education(institution="Other", institution_other=institution, location="Togo")]
    return app


def test_places_masked_but_institution_kept():
    texts, result, _ = _texts(_with_education("I am Togolese, from Lomé, Togo, and studied at Université de Lomé."))
    assert texts[0] == "I am [NATIONALITÉ], from [VILLE], [PAYS], and studied at Université de Lomé."
    # Réponse : une nationalité, une ville, un pays. Formation (« Université de Lomé, Togo ») :
    # la ville reste dans le nom gardé, le pays est masqué.
    assert {k: v for k, v in result.replacements.items() if k.startswith("place:")} == {
        "place:nationality": 1, "place:city": 1, "place:country": 2,
    }


def test_institution_places_masked_when_not_kept():
    config = CONFIG.model_copy(deep=True)
    config.places.keep_organisations = False
    texts, _, _ = _texts(_with_education("I studied at Université de Lomé."), config)
    assert texts[0] == "I studied at Université de [VILLE]."


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Benin City is not in Benin; Nigeria is not Niger.", "[VILLE] is not in [PAYS]; [PAYS] is not [PAYS]."),
        ("Côte d’Ivoire, Cote d'Ivoire and Ghanaians.", "[PAYS], [PAYS] and [NATIONALITÉ]."),
        ("A voice app in Twi and Ewe, in English.", "A voice app in [LANGUE] and [LANGUE], in English."),
        ("Mobile money is common across West Africa.", "Mobile money is common across West Africa."),
        ("I did an internship in Manchester.", "I did an internship in [LIEU]."),
    ],
)
def test_place_variants(sentence, expected):
    texts, _, _ = _texts(_app([sentence]))
    assert texts[0] == expected


def test_places_can_be_disabled():
    config = CONFIG.model_copy(deep=True)
    config.places.enabled = False
    texts, _, _ = _texts(_app(["I am Togolese, from Lomé, Togo."]), config)
    assert texts[0] == "I am Togolese, from Lomé, Togo."


def test_metadata_stays_out_of_text():
    from datetime import date

    app = _app(["Hello."], gender="Female", date_of_birth=date(2000, 6, 1), country_of_citizenship="Togo")
    _, result, _ = _texts(app)
    # Âge au 1er janvier 2027 (date de référence du guide).
    assert result.metadata.model_dump() == {"gender": "Female", "age": 26, "citizenship": "Togo"}
    assert all("Female" not in t.text and "Togo" not in t.text for t in result.texts)


# --------------------------------------------------------------------------
# Pseudonymes et table de correspondance
# --------------------------------------------------------------------------


def test_pseudonyms_are_random_and_stable(tmp_path):
    ids = [f"{n:010d}" for n in range(1001, 1041)]
    first = PseudonymTable(tmp_path / "a.json")
    names = [first.pseudonym(i) for i in ids]
    assert len(set(names)) == 40
    assert all(re.fullmatch(r"C-[0-9A-F]{8}", name) for name in names)
    assert all(i[-4:] not in name for i, name in zip(ids, names))
    first.save()
    again = PseudonymTable(tmp_path / "a.json")
    assert [again.pseudonym(i) for i in ids] == names
    other = PseudonymTable(tmp_path / "b.json")
    assert [other.pseudonym(i) for i in ids] != names
    assert stat.S_IMODE((tmp_path / "a.json").stat().st_mode) == 0o600


def test_cli_on_one_dossier(cohort, tmp_path, capsys):
    out_dir, dossiers = cohort
    app_id = dossiers[0].application.application_id
    out, table = tmp_path / "sortie", tmp_path / "secret" / "table.json"
    assert main([str(out_dir / "dossiers" / app_id), "-o", str(out), "--table", str(table)]) == 0
    pseudonym = json.loads(table.read_text(encoding="utf-8"))["entries"][app_id]
    assert (out / f"{pseudonym}.json").exists()
    assert "1 dossiers anonymisés" in capsys.readouterr().out
    # Relancer garde le même pseudonyme.
    assert main([str(out_dir / "dossiers" / app_id), "-o", str(out), "--table", str(table)]) == 0
    assert json.loads(table.read_text(encoding="utf-8"))["entries"][app_id] == pseudonym


def test_cli_refuses_table_inside_output(cohort, tmp_path):
    out_dir, _ = cohort
    out = tmp_path / "sortie"
    assert main([str(out_dir / "dossiers"), "-o", str(out), "--table", str(out / "table.json")]) == 1
    assert not (out / "table.json").exists()
