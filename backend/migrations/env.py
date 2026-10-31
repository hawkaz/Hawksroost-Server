from alembic import context

from app import config, models  # noqa: F401  (registers tables)
from app.db import Base, engine

config.ensure_dirs()
target_metadata = Base.metadata

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
