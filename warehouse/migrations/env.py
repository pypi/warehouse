# SPDX-License-Identifier: Apache-2.0

import alembic_postgresql_enum  # noqa: F401 # import activates the plugin

from alembic import context
from sqlalchemy import create_engine, pool, text

from warehouse import db


def run_migrations_offline():
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    options = context.config.get_section(context.config.config_ini_section)
    if options is None:
        raise ValueError("No options found in config")
    url = options.pop("url")
    context.configure(url=url, compare_server_default=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    options = context.config.get_section(context.config.config_ini_section)
    if options is None:
        raise ValueError("No options found in config")
    url = options.pop("url")
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        connection.execute(text("SET statement_timeout = 5000"))
        connection.execute(text("SET lock_timeout = 4000"))

        context.configure(
            connection=connection,
            target_metadata=db.metadata,
            compare_server_default=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            connection.execute(text("SELECT pg_advisory_lock(hashtext('alembic'))"))
            context.run_migrations()
            context.get_bind().commit()
            connection.execute(text("SELECT pg_advisory_unlock(hashtext('alembic'))"))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
