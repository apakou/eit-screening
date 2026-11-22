"""API : chargement, liste filtrée et triée, détail, décisions et journal."""

import json

import pytest
from fastapi.testclient import TestClient

from eit_screening.api.app import create_app
from eit_screening.api.load import load
from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata
from eit_screening.screening.common import Finding
from eit_screening.verdict.models import LlmCall, Verdict

URL = "sqlite+pysqlite:///:memory:"


def _write(folder_verdicts, folder_dossiers, pseudonym, proposed, total, findings=(), age=25):
    verdict = Verdict(
        pseudonym=pseudonym, proposed=proposed, rule="Règle.", total=total, max_total=40,
        findings=list(findings), quotes_verified=3, quotes_total=4,
        llm=LlmCall(model="m", base_url="u", attempts=1, seconds=1.0, schema_valid=True),
        created_at="2026-11-22T10:00:00",
    )
    (folder_verdicts / f"{pseudonym}.json").write_text(verdict.model_dump_json(), encoding="utf-8")
    (folder_verdicts / f"{pseudonym}.appel.json").write_text("{}", encoding="utf-8")
    dossier = AnonymizedDossier(
        pseudonym=pseudonym, metadata=Metadata(gender="Female", age=age, citizenship="Ghana"),
        texts=[AnonymizedText(section="essay", label="Q1", text="Une réponse.")],
    )
    (folder_dossiers / f"{pseudonym}.json").write_text(dossier.model_dump_json(), encoding="utf-8")


@pytest.fixture()
def client(tmp_path):
    verdicts, dossiers = tmp_path / "verdicts", tmp_path / "anonymises"
    verdicts.mkdir()
    dossiers.mkdir()
    alert = Finding(code="age_out_of_range", severity="alert", message="Âge hors tranche.")
    _write(verdicts, dossiers, "C-0000000A", "Interview Invitation", 31)
    _write(verdicts, dossiers, "C-0000000B", "Waitlist", 24)
    _write(verdicts, dossiers, "C-0000000C", "Request Final Review", 35, findings=[alert], age=33)
    app = create_app(URL)
    assert load(verdicts, dossiers, sessions=app.state.sessions) == 3
    return TestClient(app)


def test_list_sort_and_filter(client):
    rows = client.get("/api/candidates", params={"sort": "total", "order": "desc"}).json()
    assert [r["pseudonym"] for r in rows] == ["C-0000000C", "C-0000000A", "C-0000000B"]
    assert rows[0]["alerts"] == 1 and rows[0]["age"] == 33 and rows[0]["status"] == "à traiter"
    only = client.get("/api/candidates", params={"verdict": "Waitlist"}).json()
    assert [r["pseudonym"] for r in only] == ["C-0000000B"]


def test_detail(client):
    detail = client.get("/api/candidates/C-0000000A").json()
    assert detail["verdict"]["proposed"] == "Interview Invitation"
    assert detail["dossier"]["texts"][0]["text"] == "Une réponse."
    assert detail["decisions"] == []
    assert client.get("/api/candidates/C-FFFFFFFF").status_code == 404


def test_validate_keeps_both_verdicts(client):
    response = client.post("/api/candidates/C-0000000A/decisions", json={"evaluator": "Évaluatrice 1", "action": "validate"})
    assert response.status_code == 201
    decision = response.json()
    assert decision["proposed"] == decision["retained"] == "Interview Invitation"
    rows = {r["pseudonym"]: r for r in client.get("/api/candidates").json()}
    assert rows["C-0000000A"]["status"] == "validé"


def test_modify_needs_a_verdict_and_a_comment(client):
    url = "/api/candidates/C-0000000B/decisions"
    assert client.post(url, json={"evaluator": "E2", "action": "modify"}).status_code == 422
    assert client.post(url, json={"evaluator": "E2", "action": "modify", "retained": "Interview Invitation"}).status_code == 422
    same = {"evaluator": "E2", "action": "modify", "retained": "Waitlist", "comment": "Même verdict."}
    assert client.post(url, json=same).status_code == 422
    ok = {"evaluator": "E2", "action": "modify", "retained": "Interview Invitation", "comment": "Projet solide."}
    decision = client.post(url, json=ok).json()
    assert (decision["proposed"], decision["retained"]) == ("Waitlist", "Interview Invitation")


def test_journal_keeps_every_decision(client):
    url = "/api/candidates/C-0000000C/decisions"
    client.post(url, json={"evaluator": "E1", "action": "validate"})
    client.post(url, json={"evaluator": "E2", "action": "modify", "retained": "Interview Reject", "comment": "Âge."})
    journal = client.get("/api/decisions", params={"pseudonym": "C-0000000C"}).json()
    assert [(d["evaluator"], d["retained"]) for d in journal] == [
        ("E1", "Request Final Review"), ("E2", "Interview Reject"),
    ]
    detail = client.get("/api/candidates/C-0000000C").json()
    assert detail["status"] == "modifié" and detail["retained"] == "Interview Reject"
    assert len(detail["decisions"]) == 2


def test_reload_keeps_decisions(client, tmp_path):
    client.post("/api/candidates/C-0000000A/decisions", json={"evaluator": "E1", "action": "validate"})
    assert load(tmp_path / "verdicts", tmp_path / "anonymises", sessions=client.app.state.sessions) == 3
    assert len(client.get("/api/decisions").json()) == 1


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert json.loads(client.get("/openapi.json").text)["info"]["title"] == "eit-screening"
