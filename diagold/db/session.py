"""SQLAlchemy engine / session setup."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from diagold.config import DATABASE_URL, SQL_ECHO

engine: Engine = create_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    future=True,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
    """Enforce foreign keys - SQLite has them off by default."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables and run first-run seeding."""
    from diagold.db.models import Base  # noqa: WPS433 - avoid circular import
    from diagold.services.seed import seed_initial_data

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_initial_data(session)
        session.commit()
