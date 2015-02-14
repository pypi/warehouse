# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import alembic.command
import click.testing
import psycopg2
import pyramid.testing
import pytest

from pytest_dbfixtures.factories.postgresql import (
    init_postgresql_database, drop_postgresql_database,
)
from pytest_dbfixtures.utils import get_config
from sqlalchemy import event

from warehouse.config import configure
from warehouse.db import _Session


@pytest.fixture
def pyramid_request():
    return pyramid.testing.DummyRequest()


@pytest.yield_fixture
def pyramid_config(pyramid_request):
    with pyramid.testing.testConfig(request=pyramid_request) as config:
        yield config


@pytest.yield_fixture
def cli():
    runner = click.testing.CliRunner()
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture(scope="session")
def database(request, postgresql_proc):
    config = get_config(request)
    pg_host = postgresql_proc.host
    pg_port = postgresql_proc.port
    pg_user = config.postgresql.user
    pg_db = config.postgresql.db
    db_url = "postgresql://{}@{}:{}/{}".format(
        pg_user, pg_host, pg_port, pg_db,
    )

    # Create our Database.
    init_postgresql_database(psycopg2, pg_user, pg_host, pg_port, pg_db)

    # Ensure our database gets deleted.
    @request.addfinalizer
    def drop_database():
        drop_postgresql_database(psycopg2, pg_user, pg_host, pg_port, pg_db)

    # Create enough of a configuration to run the migrations.
    config = configure(
        settings={
            "env": "production",
            "database.url": db_url,
            "sessions.secret": "123456",
            "sessions.url": "redis://localhost:0/",
        },
    )

    # Actually run our migrations
    alembic.command.upgrade(config.alembic_config(), "head")

    # Give back our database url for other things to use.
    return db_url


@pytest.fixture
def app_config(database):
    # Create our configuration
    config = configure(
        settings={
            "env": "production",
            "database.url": database,
            "sessions.secret": "123456",
            "sessions.url": "redis://localhost:0/",
        },
    )

    return config


@pytest.yield_fixture
def db_session(app_config):
    engine = app_config.registry["sqlalchemy.engine"]
    conn = engine.connect()
    trans = conn.begin()
    session = _Session(bind=conn)

    # Start the session in a SAVEPOINT
    session.begin_nested()

    # Then each time that SAVEPOINT ends, reopen it
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
        engine.dispose()


@pytest.fixture
def db_request(pyramid_request, db_session):
    pyramid_request.db = db_session
    return pyramid_request
