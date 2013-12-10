# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import os
import random
import string

import alembic.config
import alembic.command
import pretend
import pytest
import sqlalchemy
import sqlalchemy.pool


def pytest_addoption(parser):
    group = parser.getgroup("warehouse")
    group._addoption(
        "--database-url",
        default=None,
        help="The url to connect when creating the test database.",
    )
    parser.addini(
        "database_url",
        "The url to connect when creating the test database.",
    )


@pytest.fixture(scope="session")
def _database_url(request):
    from warehouse.application import Warehouse

    def _get_name():
        tag = "".join(
            random.choice(string.ascii_lowercase + string.digits)
            for x in range(7)
        )
        return "warehousetest_{}".format(tag)

    def _check_name(engine, name):
        with engine.connect() as conn:
            results = conn.execute(
                "SELECT datname FROM pg_database WHERE datistemplate = false"
            )
            return name not in [r[0] for r in results]

    database_url_default = 'postgresql://localhost/test_warehouse'
    database_url_environ = os.environ.get("WAREHOUSE_DATABASE_URL")
    database_url_option = request.config.getvalue("database_url")

    if (not database_url_default and not database_url_environ
            and not database_url_option):
        pytest.skip("No database provided")

    # Configure our engine so that we can empty the database
    database_url = (
        database_url_option or database_url_environ or database_url_default
    )

    # Create the database schema
    engine = sqlalchemy.create_engine(
        database_url,
        poolclass=sqlalchemy.pool.NullPool,
    )
    app = Warehouse.from_yaml(
        override={
            "database": {"url": database_url},
            "search": {"hosts": []},
        },
        engine=engine,
        redis=False,
    )
    with app.engine.connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("CREATE EXTENSION IF NOT EXISTS citext")
        conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option(
        "script_location",
        app.config.database.migrations,
    )
    alembic_cfg.set_main_option("url", app.config.database.url)
    alembic.command.upgrade(alembic_cfg, "head")
    engine.dispose()

    return database_url


@pytest.fixture(scope="session")
def engine(_database_url):
    return sqlalchemy.create_engine(
        _database_url,
        poolclass=sqlalchemy.pool.AssertionPool,
    )


@pytest.fixture
def database(request, _database_url, engine):
    connection = engine.connect()
    transaction = connection.begin()

    def end():
        transaction.rollback()
        connection.close()

    request.addfinalizer(end)

    return connection


@pytest.fixture
def dbapp(database, _database_url):
    from warehouse.application import Warehouse

    return Warehouse.from_yaml(
        override={
            "database": {"url": _database_url},
            "search": {"hosts": []},
        },
        engine=database,
        redis=False,
    )


@pytest.fixture
def app():
    from warehouse.application import Warehouse

    def connect():
        raise RuntimeError(
            "Cannot access the database through the app fixture"
        )

    engine = pretend.stub(connect=connect)

    return Warehouse.from_yaml(
        override={
            "database": {"url": "postgresql:///nonexistant"},
            "search": {"hosts": []},
        },
        engine=engine,
        redis=False,
    )
