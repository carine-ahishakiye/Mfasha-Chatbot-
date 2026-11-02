"""SQLAlchemy engine and session factory. PostgreSQL in production, SQLite for development and tests."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mfasha.storage.orm import Base


def create_session_factory(database_url: str) -> sessionmaker:
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url or database_url == "sqlite://":
            kwargs["poolclass"] = StaticPool      # one shared connection so tests see their own data
    # Render and Heroku hand out postgres:// URLs, which SQLAlchemy 2 no longer accepts
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
