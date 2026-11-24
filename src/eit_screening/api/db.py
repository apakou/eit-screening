"""Base de données : candidatures (verdict proposé, dossier anonymisé), journal des décisions
et retours des sessions de test de l'interface.

SQLAlchemy 2 ; PostgreSQL en fonctionnement (Docker Compose), SQLite en mémoire
pour les tests. Le journal des décisions n'est jamais réécrit : chaque
validation ou modification ajoute une ligne.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

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


class TourFeedback(Base):
    """Retour d'un évaluateur à la fin de la visite guidée de la session de test.

    Une ligne par envoi, jamais réécrite. `steps` garde, pour chaque étape de la
    visite, le résultat déclaré (worked, failed, skipped) et la note éventuelle.
    """

    __tablename__ = "tour_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluator: Mapped[str] = mapped_column(String(120))
    steps: Mapped[list] = mapped_column(JSON)
    ease: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 (très difficile) à 5 (très facile)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def normalize_url(url: str) -> str:
    """Adresse au format SQLAlchemy avec le pilote psycopg (version 3).

    Supabase et la plupart des hébergeurs donnent `postgresql://…` ou
    `postgres://…`, que SQLAlchemy associerait à psycopg2, non installé.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def is_local(url: str) -> bool:
    """Vrai pour SQLite et pour une base sur cette machine (Docker Compose)."""
    if url.startswith("sqlite"):
        return True
    host = make_url(normalize_url(url)).host or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def make_engine(url: str | None = None):
    url = normalize_url(url or database_url())
    if url.startswith("sqlite") and ":memory:" in url:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith("sqlite"):
        return create_engine(url)
    # Pooler de Supabase en mode transaction (port 6543) : pas de requêtes préparées.
    options: dict = {"connect_args": {"prepare_threshold": None}}
    if os.environ.get("VERCEL"):
        # Fonction sans serveur : chaque appel peut tourner sur une instance neuve,
        # le pooler de Supabase tient les connexions à notre place.
        options["poolclass"] = NullPool
    return create_engine(url, **options)


def make_sessionmaker(engine) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)
