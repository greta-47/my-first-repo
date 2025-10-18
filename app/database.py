import os
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import sessionmaker

from app.settings import settings

DATABASE_URL = os.getenv("DATABASE_URL", settings.database_url.get_secret_value())

connect_args: Dict[str, Any] = {}
engine_kwargs: Dict[str, Any] = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    engine_kwargs["pool_size"] = settings.db_pool_size
    engine_kwargs["max_overflow"] = settings.db_max_overflow

engine_kwargs["connect_args"] = connect_args
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String, nullable=False, unique=True),
    Column("full_name", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("is_active", Integer, nullable=False, server_default="1"),
)

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

consent_scopes_table = Table(
    "consent_scopes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.email", ondelete="CASCADE"), nullable=False),
    Column("scope_type", String, nullable=False),
    Column("permissions", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

signals_table = Table(
    "signals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("signal_type", String, nullable=False),
    Column("window", String, nullable=False),
    Column("value", Float, nullable=False),
    Column("baseline", Float, nullable=True),
    Column("deviation", Float, nullable=True),
    Column("confidence", Float, nullable=False),
    Column("reason_codes", Text, nullable=False),
    Column("created_at", String, nullable=False),
)

plan_templates_table = Table(
    "plan_templates",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("template_key", String, nullable=False, unique=True),
    Column("phase", String, nullable=False),
    Column("title", String, nullable=False),
    Column("description", Text, nullable=False),
    Column("tasks", Text, nullable=False),
    Column("kpis", Text, nullable=False),
    Column("trigger_conditions", Text, nullable=True),
    Column("reading_level", Integer, nullable=False),
    Column("evidence_refs", Text, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

recovery_plans_table = Table(
    "recovery_plans",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column(
        "template_id", Integer, ForeignKey("plan_templates.id", ondelete="SET NULL"), nullable=True
    ),
    Column("phase", String, nullable=False),
    Column("status", String, nullable=False),
    Column("goals", Text, nullable=False),
    Column("tasks", Text, nullable=False),
    Column("kpis", Text, nullable=False),
    Column("review_date", String, nullable=False),
    Column("fallback_plan", Text, nullable=True),
    Column("reason_codes", Text, nullable=False),
    Column("adaptations_applied", Text, nullable=True),
    Column(
        "consent_scope_id",
        Integer,
        ForeignKey("consent_scopes.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent", String, nullable=False),
    Column("decision", String, nullable=False),
    Column("user_id_hash", String, nullable=False),
    Column("input_refs", Text, nullable=False),
    Column("rules_fired", Text, nullable=False),
    Column("outputs", Text, nullable=False),
    Column("metadata", Text, nullable=True),
    Column("created_at", String, nullable=False),
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
