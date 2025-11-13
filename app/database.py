import os
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings


class _LazyEngine:
    """Lazy engine wrapper that defers initialization until first access."""

    def __init__(self):
        self._engine: Optional[Engine] = None

    def _ensure_initialized(self) -> Engine:
        """Ensure the database engine is initialized. Creates it on first call."""
        if self._engine is not None:
            return self._engine

        database_url = os.getenv("DATABASE_URL") or settings.database_url.get_secret_value()

        connect_args: Dict[str, Any] = {}
        engine_kwargs: Dict[str, Any] = {}

        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        else:
            engine_kwargs["pool_size"] = settings.db_pool_size
            engine_kwargs["max_overflow"] = settings.db_max_overflow

        engine_kwargs["connect_args"] = connect_args

        self._engine = create_engine(database_url, **engine_kwargs)
        SessionLocal.configure(bind=self._engine)

        return self._engine

    def __getattr__(self, name):
        """Delegate all attribute access to the underlying engine."""
        return getattr(self._ensure_initialized(), name)


engine = _LazyEngine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

metadata = MetaData()

consents_table = Table(
    "consents",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("terms_version", String, nullable=False),
    Column("accepted", Boolean, nullable=False),
    Column("recorded_at", String, nullable=False),
)

checkins_table = Table(
    "checkins",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("adherence", Integer, nullable=False),
    Column("mood_trend", Integer, nullable=False),
    Column("cravings", Integer, nullable=False),
    Column("sleep_hours", Float, nullable=False),
    Column("isolation", Integer, nullable=False),
    Column("ts", String, nullable=False),
)


def create_tables():
    """Create all tables. Initializes engine on first call."""
    metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
