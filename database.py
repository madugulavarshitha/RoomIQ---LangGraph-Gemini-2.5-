"""
Database engine and session management.

Uses SQLAlchemy against DATABASE_URL. Defaults to a local SQLite file so
the project runs with zero external setup; point DATABASE_URL at a
PostgreSQL instance in production without changing any application code.
"""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for use outside of request handlers (agents, seeding)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app.database import models  # noqa: F401  (ensure models are registered)
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # Auto-migrate SQLite columns if table already exists
    with engine.connect() as conn:
        insp = inspect(engine)
        if "bookings" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("bookings")}
            if "allocated_chairs" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN allocated_chairs INTEGER"))
            if "attendee_names" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN attendee_names VARCHAR(500) DEFAULT ''"))
            if "attended_names" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN attended_names VARCHAR(500) DEFAULT ''"))
            if "absent_names" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN absent_names VARCHAR(500) DEFAULT ''"))
            if "actual_attendees_count" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN actual_attendees_count INTEGER"))
            if "meeting_type" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_type VARCHAR(60) DEFAULT 'General Meeting'"))
            if "meeting_outcome" not in cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_outcome VARCHAR(40) DEFAULT 'COMPLETED'"))
            conn.commit()
