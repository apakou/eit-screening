"""API FastAPI : liste des candidatures, détail d'un dossier, décision de l'évaluateur, journal,
retours de la session de test.

Le système propose, l'évaluateur tranche. Guide 2027 : une décision prend trois
valeurs (Interview Invitation, Interview Reject, Waitlist) et un booléen
distinct, la demande de revue complémentaire. Chaque décision garde les valeurs
proposées et retenues des deux, avec l'évaluateur, la date et le commentaire.
Pas d'authentification dans le prototype (Keycloak appartient à l'architecture
cible) : l'évaluateur est déclaré dans la requête. Une fois l'API en ligne, un
code d'accès partagé (variable EIT_ACCESS_CODE, en-tête X-Access-Code) garde
le journal des décisions des visiteurs de passage ; ce n'est pas une identité.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .db import Candidate, Decision, TourFeedback, make_engine, make_sessionmaker, now

VERDICTS = ("Interview Invitation", "Interview Reject", "Waitlist")
VerdictLabel = Literal["Interview Invitation", "Interview Reject", "Waitlist"]


class DecisionIn(BaseModel):
    evaluator: str = Field(min_length=1, max_length=120)
    action: Literal["validate", "modify"]
    retained: VerdictLabel | None = None
    request_further_review: bool | None = None  # modification : valeur retenue (défaut : celle proposée)
    comment: str = ""

    @model_validator(mode="after")
    def _check(self) -> DecisionIn:
        if self.action == "modify":
            if self.retained is None:
                raise ValueError("A modification must give the decision retained.")
            if not self.comment.strip():
                raise ValueError("A modification must be explained in a comment.")
        return self


class DecisionOut(BaseModel):
    id: int
    pseudonym: str
    evaluator: str
    action: str
    proposed: str | None
    retained: str
    proposed_review: bool
    retained_review: bool
    comment: str
    created_at: datetime


class CandidateSummary(BaseModel):
    pseudonym: str
    proposed: str | None
    request_further_review: bool
    total: int | None
    max_total: int
    alerts: int
    concerns: int
    quotes_verified: int
    quotes_total: int
    gender: str | None = None
    age: int | None = None
    citizenship: str | None = None
    status: Literal["pending", "validated", "modified"]
    retained: str | None = None
    retained_review: bool | None = None


class CandidateDetail(CandidateSummary):
    verdict: dict
    dossier: dict
    decisions: list[DecisionOut]


class StepResult(BaseModel):
    step: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=200)
    result: Literal["worked", "failed", "skipped"]
    note: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def _check(self) -> StepResult:
        if self.result == "failed" and not self.note.strip():
            raise ValueError("A step that did not work must say what happened.")
        return self


class FeedbackIn(BaseModel):
    evaluator: str = Field(min_length=1, max_length=120)
    steps: list[StepResult] = Field(max_length=100)
    ease: int | None = Field(default=None, ge=1, le=5)
    comment: str = Field(default="", max_length=8000)


class FeedbackOut(FeedbackIn):
    id: int
    created_at: datetime


def _feedback_out(row: TourFeedback) -> FeedbackOut:
    return FeedbackOut(
        id=row.id, evaluator=row.evaluator, steps=row.steps, ease=row.ease, comment=row.comment,
        created_at=row.created_at,
    )


def _decision_out(row: Decision) -> DecisionOut:
    return DecisionOut(
        id=row.id, pseudonym=row.pseudonym, evaluator=row.evaluator, action=row.action, proposed=row.proposed,
        retained=row.retained, proposed_review=row.proposed_review, retained_review=row.retained_review,
        comment=row.comment, created_at=row.created_at,
    )


def _summary(candidate: Candidate, last: Decision | None) -> dict:
    meta = candidate.metadata_json or {}
    return dict(
        pseudonym=candidate.pseudonym, proposed=candidate.proposed,
        request_further_review=candidate.request_further_review, total=candidate.total,
        max_total=candidate.max_total, alerts=candidate.alerts, concerns=candidate.concerns,
        quotes_verified=candidate.quotes_verified, quotes_total=candidate.quotes_total,
        gender=meta.get("gender"), age=meta.get("age"), citizenship=meta.get("citizenship"),
        status="pending" if last is None else ("validated" if last.action == "validate" else "modified"),
        retained=None if last is None else last.retained,
        retained_review=None if last is None else last.retained_review,
    )


LOCAL_ORIGINS = ["http://localhost:3100", "http://127.0.0.1:3100"]
OPEN_PATHS = {"/api/health"}


def _origins_from_env() -> list[str]:
    extra = [o.strip() for o in os.environ.get("EIT_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return LOCAL_ORIGINS + extra


def create_app(
    database_url: str | None = None,
    allowed_origins: list[str] | None = None,
    access_code: str | None = None,
) -> FastAPI:
    """``access_code`` (défaut : EIT_ACCESS_CODE) : exigé sur toutes les routes /api sauf /api/health."""
    engine = make_engine(database_url)
    sessions: sessionmaker[Session] = make_sessionmaker(engine)
    code = access_code if access_code is not None else os.environ.get("EIT_ACCESS_CODE", "")
    app = FastAPI(title="eit-screening", description="Proposed decisions and evaluator decisions (MEST pre-screening).")

    @app.middleware("http")
    async def check_access_code(request: Request, call_next):
        path = request.url.path
        if code and request.method != "OPTIONS" and path.startswith("/api/") and path not in OPEN_PATHS:
            given = request.headers.get("X-Access-Code", "")
            if not given:
                return JSONResponse({"detail": "Access code required."}, status_code=401)
            if not secrets.compare_digest(given.encode(), code.encode()):
                return JSONResponse({"detail": "Wrong access code."}, status_code=401)
        return await call_next(request)

    # Ajouté après le contrôle du code, donc exécuté avant : les refus 401 portent aussi les en-têtes CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or _origins_from_env(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Access-Code"],
    )
    app.state.sessions = sessions

    def session():
        with sessions() as db:
            yield db

    def last_decisions(db: Session) -> dict[str, Decision]:
        latest: dict[str, Decision] = {}
        for row in db.scalars(select(Decision).order_by(Decision.created_at, Decision.id)):
            latest[row.pseudonym] = row
        return latest

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/access")
    def access() -> dict:
        """Répond 200 si le code d'accès envoyé est bon (ou si aucun code n'est exigé)."""
        return {"status": "ok", "code_required": bool(code)}

    @app.get("/api/candidates", response_model=list[CandidateSummary])
    def candidates(
        verdict: VerdictLabel | None = None,
        review: bool | None = None,
        status: Literal["pending", "validated", "modified"] | None = None,
        sort: Literal["pseudonym", "total", "alerts"] = "pseudonym",
        order: Literal["asc", "desc"] = "asc",
        db: Session = Depends(session),
    ):
        latest = last_decisions(db)
        rows = [_summary(c, latest.get(c.pseudonym)) for c in db.scalars(select(Candidate))]
        if verdict:
            rows = [r for r in rows if r["proposed"] == verdict]
        if review is not None:
            rows = [r for r in rows if r["request_further_review"] == review]
        if status:
            rows = [r for r in rows if r["status"] == status]
        # Les valeurs absentes (pas de total) restent en fin de liste, quel que soit le sens.
        present = sorted((r for r in rows if r[sort] is not None), key=lambda r: r[sort], reverse=order == "desc")
        return present + [r for r in rows if r[sort] is None]

    @app.get("/api/candidates/{pseudonym}", response_model=CandidateDetail)
    def candidate(pseudonym: str, db: Session = Depends(session)):
        row = db.get(Candidate, pseudonym)
        if row is None:
            raise HTTPException(404, "Unknown application.")
        history = list(db.scalars(
            select(Decision).where(Decision.pseudonym == pseudonym).order_by(Decision.created_at, Decision.id)
        ))
        return {
            **_summary(row, history[-1] if history else None),
            "verdict": row.verdict,
            "dossier": row.dossier,
            "decisions": [_decision_out(d) for d in history],
        }

    @app.post("/api/candidates/{pseudonym}/decisions", response_model=DecisionOut, status_code=201)
    def decide(pseudonym: str, body: DecisionIn, db: Session = Depends(session)):
        row = db.get(Candidate, pseudonym)
        if row is None:
            raise HTTPException(404, "Unknown application.")
        if body.action == "validate":
            if row.proposed is None:
                raise HTTPException(422, "No decision was proposed: use “modify” to choose one.")
            retained, review = row.proposed, row.request_further_review
        else:
            retained = body.retained
            review = row.request_further_review if body.request_further_review is None else body.request_further_review
            if retained == row.proposed and review == row.request_further_review:
                raise HTTPException(422, "Same decision and review flag as proposed: use “validate” instead.")
        decision = Decision(
            pseudonym=pseudonym, evaluator=body.evaluator.strip(), action=body.action, proposed=row.proposed,
            retained=retained, proposed_review=row.request_further_review, retained_review=review,
            comment=body.comment.strip(), created_at=now(),
        )
        db.add(decision)
        db.commit()
        return _decision_out(decision)

    @app.get("/api/decisions", response_model=list[DecisionOut])
    def decisions(pseudonym: str | None = Query(default=None), db: Session = Depends(session)):
        query = select(Decision).order_by(Decision.created_at, Decision.id)
        if pseudonym:
            query = query.where(Decision.pseudonym == pseudonym)
        return [_decision_out(d) for d in db.scalars(query)]

    @app.post("/api/feedback", response_model=FeedbackOut, status_code=201)
    def add_feedback(body: FeedbackIn, db: Session = Depends(session)):
        if not body.evaluator.strip():
            raise HTTPException(422, "Enter your name before sending feedback.")
        row = TourFeedback(
            evaluator=body.evaluator.strip(), steps=[s.model_dump() for s in body.steps], ease=body.ease,
            comment=body.comment.strip(), created_at=now(),
        )
        db.add(row)
        db.commit()
        return _feedback_out(row)

    @app.get("/api/feedback", response_model=list[FeedbackOut])
    def feedback(db: Session = Depends(session)):
        return [_feedback_out(r) for r in db.scalars(select(TourFeedback).order_by(TourFeedback.created_at, TourFeedback.id))]

    return app


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Lance l'API (base : variable EIT_DATABASE_URL).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0
