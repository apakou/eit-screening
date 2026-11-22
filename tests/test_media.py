"""Pièces jointes (Docling, OCR) et vidéos (FFmpeg, faster-whisper), puis anonymisation du texte obtenu.

Ces tests chargent de vrais modèles : Docling sur un seul dossier, Whisper
(modèle par défaut) sur une courte vidéo dont la voix est synthétisée par FFmpeg (flite).
"""

import json
import re
import subprocess
import unicodedata

import pytest
from rapidfuzz import fuzz

from eit_screening.media.attachments import read_attachments
from eit_screening.media.config import load_config
from eit_screening.media.extract import check_certificates, find_video, transcripts_for
from eit_screening.media.transcribe import extract_audio, read_text_transcript, transcribe_video
from eit_screening.models import Application, Personal
from eit_screening.privacy.anonymize import anonymize_dossier
from eit_screening.privacy.anonymize import load_config as load_anonymize_config

SPOKEN = [
    "Hello, my name is Kofi Mensah.",
    "I am applying to the startup program because I want to build software for farmers.",
]


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def _whisper_config():
    """Modèle par défaut (« small ») : « tiny » entend « Gofima » pour « Kofi Mensah »."""
    return load_config()


@pytest.fixture(scope="module")
def spoken_video(tmp_path_factory):
    """Vidéo de deux phrases séparées par un silence, voix synthétisée par FFmpeg (flite)."""
    folder = tmp_path_factory.mktemp("video")
    video = folder / "personal_statement.mp4"
    graph = (
        f"flite=text='{SPOKEN[0]}':voice=slt[a];anullsrc=r=16000:cl=mono,atrim=0:2[s];"
        f"flite=text='{SPOKEN[1]}':voice=slt[b];[a][s][b]concat=n=3:v=0:a=1[out]"
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex", graph,
        "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=5", "-map", "0:v", "-map", "[out]",
        "-shortest", "-c:v", "libx264", "-c:a", "aac", str(video),
    ]
    subprocess.run(command, check=True)
    return video


@pytest.fixture(scope="module")
def transcript(spoken_video):
    return transcribe_video(spoken_video, _whisper_config())


# --- Transcription ------------------------------------------------------------


def test_transcription_keeps_timestamps(transcript):
    """Critère d'acceptation : chaque segment garde son début et sa fin."""
    assert transcript.source == "faster-whisper" and transcript.model == load_config().transcription.model
    assert len(transcript.segments) >= 2  # deux phrases séparées par un silence
    previous_end = 0.0
    for segment in transcript.segments:
        assert segment.start is not None and segment.end is not None
        assert previous_end - 0.01 <= segment.start < segment.end <= transcript.duration + 0.5
        assert segment.avg_logprob is not None and segment.no_speech_prob is not None
        previous_end = segment.end
    assert fuzz.token_set_ratio(_fold(transcript.text), _fold(" ".join(SPOKEN))) >= 70


def test_text_transcript_has_no_invented_timestamps(tmp_path):
    path = tmp_path / "personal_statement.txt"
    path.write_text("Hello, I am Ama.\n", encoding="utf-8")
    transcript = read_text_transcript(path)
    assert transcript.source == "text_file"
    assert [(s.start, s.end, s.text) for s in transcript.segments] == [(None, None, "Hello, I am Ama.")]


def test_extract_audio_reports_ffmpeg_errors(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_text("pas une vidéo", encoding="utf-8")
    with pytest.raises(RuntimeError, match="FFmpeg"):
        extract_audio(broken, tmp_path / "audio.wav")


def test_video_beside_pdf_wins_over_text(spoken_video, tmp_path):
    folder = spoken_video.parent
    (folder / "personal_statement.txt").write_text("Texte écrit.", encoding="utf-8")
    (folder / "assessment_reflection.txt").write_text("Réflexion écrite.", encoding="utf-8")
    config = _whisper_config()
    assert find_video(folder, "personal_statement", config) == spoken_video
    found = transcripts_for(folder, config)
    assert found["personal_statement"].source == "faster-whisper"
    assert found["assessment_reflection"].source == "text_file"


def test_spoken_name_is_masked_even_when_misheard(transcript):
    """Whisper peut écrire « Mensa » pour « Mensah » : la couche approchée le masque quand même."""
    app = Application(application_id="1", personal=Personal(first_name="Kofi", last_name="Mensah"))
    config = load_anonymize_config()
    result, _ = anonymize_dossier(app, "C-TEST", {"personal_statement": transcript}, config)
    spoken = [t for t in result.texts if t.section == "personal_statement"]
    assert len(spoken) == len(transcript.segments)
    assert [(t.start, t.end) for t in spoken] == [(s.start, s.end) for s in transcript.segments]
    joined = " ".join(t.text for t in spoken)
    assert "[CANDIDAT]" in joined
    for word in re.findall(r"[^\W\d_]+", _fold(joined)):
        assert fuzz.ratio(word, "mensah") < 80 and word != "kofi", word


def test_approximate_masking_only_for_noisy_text():
    app = Application(application_id="1", personal=Personal(first_name="Kofi", last_name="Mensah"))
    config = load_anonymize_config()
    config.ner.enabled = False
    from eit_screening.privacy.anonymize import Masker

    masker = Masker(app, config)
    assert masker.mask("I am Kofi Mensa.", noisy=True) == "I am [CANDIDAT] [CANDIDAT]."
    assert masker.mask("I am Kofi Mensa.") == "I am [CANDIDAT] Mensa."
    assert masker.mask("Please mention it.", noisy=True) == "Please mention it."


def test_approximate_places_respect_kept_institutions_and_common_words():
    from eit_screening.models import Education
    from eit_screening.privacy.anonymize import Masker

    app = Application(
        application_id="1",
        personal=Personal(first_name="Kofi", last_name="Mensah", country_of_residence="Ghana"),
        education=[Education(institution="University of Ghana", location="Ghana")],
    )
    config = load_anonymize_config()
    config.ner.enabled = False
    masker = Masker(app, config)
    assert masker.mask("I studied at University of Ghana.", noisy=True) == "I studied at University of Ghana."
    assert masker.mask("I live near Ouagadougu, Ghanna.", noisy=True) == "I live near [VILLE], [PAYS]."
    for sentence in ("I deployed a server.", "The librarian mended an alien device."):
        assert masker.mask(sentence, noisy=True) == sentence


# --- Pièces jointes -------------------------------------------------------------


@pytest.fixture(scope="module")
def ocr_dossier(cohort, parsed):
    """Premier dossier de la cohorte qui a au moins deux certificats en image, relu par Docling."""
    out_dir, dossiers = cohort
    for dossier in dossiers:
        if sum(c.as_image for c in dossier.certificates) >= 2:
            app_id = dossier.application.application_id
            folder = out_dir / "dossiers" / app_id
            app = parsed[app_id]
            pages = read_attachments(folder / "application.pdf", app)
            truth = json.loads((folder / "pieces_jointes.json").read_text(encoding="utf-8"))
            return folder, app, pages, truth
    raise AssertionError("aucun dossier avec deux certificats en image")


def test_image_certificates_are_read(ocr_dossier):
    """Critère d'acceptation : le texte des certificats en image est récupéré."""
    _, app, pages, truth = ocr_dossier
    assert [p.page_number for p in pages] == [p.page_number for p in app.attachment_pages]
    for page in pages:
        assert page.text_source == ("ocr" if page.needs_ocr else "docling")
        assert page.text.strip()
    images = [c for c in check_certificates(pages, truth) if c.as_image]
    assert len(images) >= 2
    for check in images:
        assert check.similarity >= 85, check
        # L'OCR peut inverser prénom et nom : chaque mot du nom doit être lu, dans n'importe quel ordre.
        assert check.name_words_found, check


def test_ocr_text_is_anonymized(ocr_dossier):
    """Le nom lu sur un certificat scanné ne passe pas dans le texte anonymisé."""
    _, app, pages, _ = ocr_dossier
    enriched = app.model_copy(update={"attachment_pages": pages})
    result, _ = anonymize_dossier(enriched, "C-TEST")
    tokens = [t for t in re.split(r"[\s-]+", _fold(f"{app.personal.first_name} {app.personal.last_name}")) if len(t) >= 2]
    ocr_pages = {p.page_number for p in pages if p.text_source == "ocr"}
    texts = [t.text for t in result.texts if t.section == "attachment" and t.page in ocr_pages]
    assert texts
    for word in re.findall(r"[^\W\d_]+", _fold(" ".join(texts))):
        for token in tokens:
            assert word != token and (len(token) < 4 or fuzz.ratio(word, token) < 85), (word, token)
