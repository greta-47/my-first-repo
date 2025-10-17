import os
from typing import Any, Dict

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings

DATABASE_URL = os.getenv("DATABASE_URL", settings.database_url.get_secret_value())

connect_args: Dict[str, Any] = {}
engine_kwargs: Dict[str, Any] = {"connect_args": connect_args}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = settings.db_pool_size
    engine_kwargs["max_overflow"] = settings.db_max_overflow

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    """Create all tables. Uses the current global engine reference."""
    global engine
    metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
