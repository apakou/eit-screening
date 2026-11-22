"""Base de données : candidatures (verdict proposé, dossier anonymisé) et journal des décisions.

SQLAlchemy 2 ; PostgreSQL en fonctionnement (Docker Compose), SQLite en mémoire
pour les tests. Le journal des décisions n'est jamais réécrit : chaque
validation ou modification ajoute une ligne.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_URL = "postgresql+psycopg://eit:eit@127.0.0.1:5433/eit"


def database_url() -> str:
    return os.environ.get("EIT_DATABASE_URL", DEFAULT_URL)


class Base(DeclarativeBase):
    pass


class Candidate(Base):
    __tablename__ = "candidates"

    pseudonym: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Décision proposée (trois valeurs, ou vide si rien n'est proposable) et revue complémentaire.
    proposed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_further_review: Mapped[bool] = mapped_column(Boolean, default=False)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_total: Mapped[int] = mapped_column(Integer)
    alerts: Mapped[int] = mapped_column(Integer, default=0)
    concerns: Mapped[int] = mapped_column(Integer, default=0)
    quotes_verified: Mapped[int] = mapped_column(Integer, default=0)
    quotes_total: Mapped[int] = mapped_column(Integer, default=0)
    # Métadonnées (genre, âge, nationalité) : pour les filtres, jamais envoyées au modèle.
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON)
    verdict: Mapped[dict] = mapped_column(JSON)
    dossier: Mapped[dict] = mapped_column(JSON)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pseudonym: Mapped[str] = mapped_column(ForeignKey("candidates.pseudonym"), index=True)
    evaluator: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(16))  # validate | modify
    proposed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retained: Mapped[str] = mapped_column(String(32))
    proposed_review: Mapped[bool] = mapped_column(Boolean)
    retained_review: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def make_engine(url: str | None = None):
    url = url or database_url()
    if url.startswith("sqlite") and ":memory:" in url:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url)


def make_sessionmaker(engine) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)
