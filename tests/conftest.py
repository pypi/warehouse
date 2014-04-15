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
import subprocess
import os

from sqlalchemy.engine import create_engine
from sqlalchemy.pool import AssertionPool
import alembic.config
import alembic.command
import pretend
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        # Mark any item with one of the database fixture as using the db
        if set(getattr(item, "funcargnames", [])) & {"engine", "database"}:
            item.add_marker(pytest.mark.db)


@pytest.fixture(scope='session')
def database(request):
    """Creates the warehouse_unittest database, builds the schema and returns
    an SQLALchemy Connection to the database.
    """

    if os.getenv('WAREHOUSE_DATABASE_URL'):
        # Assume that the database was externally created
        url = os.getenv('WAREHOUSE_DATABASE_URL')
    else:
        # (Drop and) create the warehouse_unittest database with UTF-8 encoding
        # (in case the default encoding was changed from UTF-8)
        subprocess.call(['dropdb', 'warehouse_unittest'])
        subprocess.check_call(['createdb', '-E', 'UTF8', 'warehouse_unittest'])
        url = 'postgresql:///warehouse_unittest'

    engine = create_engine(url, poolclass=AssertionPool)

    request.addfinalizer(engine.dispose)

    if not os.getenv('WAREHOUSE_DATABASE_URL'):
        request.addfinalizer(
            lambda: subprocess.call(['dropdb', 'warehouse_unittest'])
        )

    # Connect to the database and create the necessary extensions
    engine.execute('CREATE EXTENSION IF NOT EXISTS "citext"')
    engine.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Have Alembic create the schema
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option(
        "script_location",
        "warehouse:migrations",
    )
    alembic_cfg.set_main_option("url", url)
    alembic.command.upgrade(alembic_cfg, "head")

    return engine


@pytest.fixture
def engine(request, database):
    connection = database.connect()
    transaction = connection.begin_nested()
    request.addfinalizer(transaction.rollback)
    request.addfinalizer(connection.close)
    return connection


class ErrorRedis:
    def __init__(self, url):
        self.url = url

    @classmethod
    def from_url(cls, url):
        return ErrorRedis(url)

    def __getattr__(self, name):
        raise RuntimeError("Cannot access redis")


@pytest.fixture
def dbapp(engine):
    from warehouse.application import Warehouse

    return Warehouse.from_yaml(
        override={
            "site": {
                "access_token": "testing",
                "hosts": "localhost",
            },
            "redis": {
                "downloads": "redis://nonexistant/0",
                "sessions": "redis://nonexistant/0",
            },
            "search": {"hosts": []},
        },
        engine=engine,
        redis_class=ErrorRedis,
    )


@pytest.fixture
def app():
    from warehouse.application import Warehouse

    def connect():
        raise RuntimeError(
            "Cannot access the database through the app fixture"
        )

    return Warehouse.from_yaml(
        override={
            "site": {
                "access_token": "testing",
                "hosts": "localhost",
            },
            "database": {"url": "postgresql:///nonexistant"},
            "redis": {
                "downloads": "redis://nonexistant/0",
                "sessions": "redis://nonexistant/0",
            },
            "search": {"hosts": []},
        },
        engine=pretend.stub(connect=connect, execute=connect),
        redis_class=ErrorRedis,
    )
