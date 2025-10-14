import os
from logging.config import fileConfig
from typing import Optional

from sqlalchemy import engine_from_config, pool

from alembic import context  # type: ignore[attr-defined]

config = context.config

cfg_path: Optional[str] = None
if config is not None and getattr(config, "config_file_name", None):
    cfg_path = str(config.config_file_name)
    fileConfig(cfg_path)  # type: ignore[arg-type]

target_metadata = None
try:
    from app.database import metadata

    target_metadata = metadata
except Exception:
    target_metadata = None


def run_migrations_offline():
    url = os.getenv("DATABASE_URL")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
