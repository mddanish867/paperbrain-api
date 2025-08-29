import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# --- Make sure the project root is importable ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---- Alembic config ----
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- Import your app's Base and settings ----
from app.db.base import Base  # <-- your declarative Base
from app.core.config import settings

# IMPORTANT: import models so autogenerate "sees" them
# (add more as you create them)
from app.db.models.user import User  # noqa: F401

# target metadata for 'autogenerate'
target_metadata = Base.metadata

def get_url() -> str:
    # Use the same DSN your app uses
    # Ensure sslmode=require for Supabase
    return str(settings.DATABASE_URL)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    # We create engine ourselves so we can enforce SSL for Supabase
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
