"""Engine/session plumbing. The engine is created lazily so importing the app never needs a DB."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        SessionLocal.configure(bind=_engine)
    return _engine


def get_db():
    """FastAPI dependency: one session per request."""
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_sqlite_memory_engine():
    """In-memory SQLite engine with foreign keys ON (used by tests and scripts/demo.py)."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
