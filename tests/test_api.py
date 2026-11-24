"""API : chargement, liste filtrée et triée, détail, décisions et journal."""

import json

import pytest
from fastapi.testclient import TestClient

from eit_screening.api.app import create_app
from eit_screening.api.db import is_local, normalize_url
from eit_screening.api.load import load, main as load_main
from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata
from eit_screening.screening.common import Finding
from eit_screening.verdict.models import LlmCall, Verdict

URL = "sqlite+pysqlite:///:memory:"


def _write(folder_verdicts, folder_dossiers, pseudonym, proposed, total, findings=(), age=25, review=False):
    verdict = Verdict(
        pseudonym=pseudonym, proposed=proposed, request_further_review=review, rule="Règle.", total=total, max_total=40,
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
    _write(verdicts, dossiers, "C-0000000C", "Interview Reject", 35, findings=[alert], age=36, review=True)
    _write(verdicts, dossiers, "C-0000000D", None, None, review=True)
    app = create_app(URL)
    assert load(verdicts, dossiers, sessions=app.state.sessions) == 4
    return TestClient(app)


def test_list_sort_and_filter(client):
    rows = client.get("/api/candidates", params={"sort": "total", "order": "desc"}).json()
    assert [r["pseudonym"] for r in rows] == ["C-0000000C", "C-0000000A", "C-0000000B", "C-0000000D"]
    assert rows[0]["alerts"] == 1 and rows[0]["age"] == 36 and rows[0]["status"] == "pending"
    only = client.get("/api/candidates", params={"verdict": "Waitlist"}).json()
    assert [r["pseudonym"] for r in only] == ["C-0000000B"]
    review = client.get("/api/candidates", params={"review": True}).json()
    assert {r["pseudonym"] for r in review} == {"C-0000000C", "C-0000000D"}
    assert client.get("/api/candidates", params={"verdict": "Request Final Review"}).status_code == 422


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
    assert decision["proposed_review"] is decision["retained_review"] is False
    rows = {r["pseudonym"]: r for r in client.get("/api/candidates").json()}
    assert rows["C-0000000A"]["status"] == "validated"


def test_modify_needs_a_verdict_and_a_comment(client):
    url = "/api/candidates/C-0000000B/decisions"
    assert client.post(url, json={"evaluator": "E2", "action": "modify"}).status_code == 422
    assert client.post(url, json={"evaluator": "E2", "action": "modify", "retained": "Interview Invitation"}).status_code == 422
    same = {"evaluator": "E2", "action": "modify", "retained": "Waitlist", "comment": "Même verdict."}
    assert client.post(url, json=same).status_code == 422
    old = {"evaluator": "E2", "action": "modify", "retained": "Request Final Review", "comment": "Ancienne valeur."}
    assert client.post(url, json=old).status_code == 422
    ok = {"evaluator": "E2", "action": "modify", "retained": "Interview Invitation", "comment": "Projet solide."}
    decision = client.post(url, json=ok).json()
    assert (decision["proposed"], decision["retained"]) == ("Waitlist", "Interview Invitation")


def test_review_flag_alone_can_be_modified(client):
    url = "/api/candidates/C-0000000B/decisions"
    body = {"evaluator": "E3", "action": "modify", "retained": "Waitlist", "request_further_review": True,
            "comment": "Projet à revoir en comité."}
    decision = client.post(url, json=body).json()
    assert (decision["retained"], decision["proposed_review"], decision["retained_review"]) == ("Waitlist", False, True)


def test_nothing_to_validate_without_a_proposal(client):
    url = "/api/candidates/C-0000000D/decisions"
    assert client.post(url, json={"evaluator": "E1", "action": "validate"}).status_code == 422
    body = {"evaluator": "E1", "action": "modify", "retained": "Waitlist", "comment": "Choix manuel."}
    decision = client.post(url, json=body).json()
    assert decision["proposed"] is None and decision["retained"] == "Waitlist" and decision["retained_review"] is True


def test_journal_keeps_every_decision(client):
    url = "/api/candidates/C-0000000C/decisions"
    client.post(url, json={"evaluator": "E1", "action": "validate"})
    client.post(url, json={"evaluator": "E2", "action": "modify", "retained": "Waitlist",
                           "request_further_review": False, "comment": "Âge vérifié."})
    journal = client.get("/api/decisions", params={"pseudonym": "C-0000000C"}).json()
    assert [(d["evaluator"], d["retained"], d["retained_review"]) for d in journal] == [
        ("E1", "Interview Reject", True), ("E2", "Waitlist", False),
    ]
    detail = client.get("/api/candidates/C-0000000C").json()
    assert detail["status"] == "modified" and detail["retained"] == "Waitlist" and detail["retained_review"] is False
    assert len(detail["decisions"]) == 2


def test_reload_keeps_decisions(client, tmp_path):
    client.post("/api/candidates/C-0000000A/decisions", json={"evaluator": "E1", "action": "validate"})
    assert load(tmp_path / "verdicts", tmp_path / "anonymises", sessions=client.app.state.sessions) == 4
    assert len(client.get("/api/decisions").json()) == 1


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert json.loads(client.get("/openapi.json").text)["info"]["title"] == "eit-screening"


def test_feedback_is_kept_with_each_step(client):
    body = {
        "evaluator": "E1", "ease": 4, "comment": "Clair.",
        "steps": [
            {"step": "filters", "title": "Filter by decision", "result": "worked"},
            {"step": "quotes", "title": "Check a quote", "result": "failed", "note": "La citation ne s'affiche pas."},
            {"step": "log", "title": "Decision log", "result": "skipped"},
        ],
    }
    saved = client.post("/api/feedback", json=body).json()
    assert saved["id"] and saved["ease"] == 4
    listed = client.get("/api/feedback").json()
    assert [s["result"] for s in listed[0]["steps"]] == ["worked", "failed", "skipped"]


def test_feedback_needs_a_name_and_a_note_on_failures(client):
    failed = {"step": "quotes", "result": "failed", "note": " "}
    assert client.post("/api/feedback", json={"evaluator": "E1", "steps": [failed]}).status_code == 422
    assert client.post("/api/feedback", json={"evaluator": "  ", "steps": []}).status_code == 422
    assert client.post("/api/feedback", json={"evaluator": "E1", "steps": [], "ease": 6}).status_code == 422
    assert client.get("/api/feedback").json() == []


def test_hosted_urls_use_psycopg_and_are_not_local():
    hosted = "postgresql://postgres.abc:secret@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    assert normalize_url(hosted).startswith("postgresql+psycopg://postgres.abc:")
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert not is_local(hosted)
    assert is_local("postgresql+psycopg://eit:eit@127.0.0.1:5433/eit") and is_local(URL)


def test_loading_a_hosted_database_needs_the_fictional_data_flag(tmp_path, capsys):
    hosted = "postgresql://u:p@db.example.supabase.co:5432/postgres"
    assert load_main(["--verdicts", str(tmp_path), "--anonymises", str(tmp_path), "--database-url", hosted]) == 2
    assert "données fictives" in capsys.readouterr().err


def test_access_code_guards_every_route_but_health():
    app = create_app(URL, access_code="mest-2027")
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/candidates").json() == {"detail": "Access code required."}
    assert c.get("/api/candidates", headers={"X-Access-Code": "faux"}).status_code == 401
    assert c.post("/api/feedback", json={"evaluator": "E1", "steps": []}).status_code == 401
    ok = {"X-Access-Code": "mest-2027"}
    assert c.get("/api/candidates", headers=ok).status_code == 200
    assert c.get("/api/access", headers=ok).json() == {"status": "ok", "code_required": True}


def test_no_access_code_means_open_api(client):
    assert client.get("/api/access").json() == {"status": "ok", "code_required": False}


def test_refusals_carry_cors_headers():
    c = TestClient(create_app(URL, access_code="mest-2027"))
    r = c.get("/api/candidates", headers={"Origin": "http://localhost:3100"})
    assert r.status_code == 401 and r.headers["access-control-allow-origin"] == "http://localhost:3100"
