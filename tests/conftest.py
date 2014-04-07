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
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.parse

import pretend
import pytest

import alembic.config
import alembic.command
import psycopg2
import psycopg2.extensions
import sqlalchemy
import sqlalchemy.pool


def pytest_collection_modifyitems(items):
    for item in items:
        # Mark any item with one of the database fixture as using the db
        if set(getattr(item, "funcargnames", [])) & {"postgresql", "database"}:
            item.add_marker(pytest.mark.db)


def pytest_addoption(parser):
    group = parser.getgroup("warehouse")
    group.addoption(
        "--database-url",
        default=None,
        help="An url to an already created warehouse test database",
    )


def _get_open_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)

    port = s.getsockname()[1]

    s.close()

    return port


@pytest.fixture(scope="session")
def postgresql(request):
    # First check to see if we've been given a database url that we should use
    # instead
    database_url = (
        os.environ.get("WAREHOUSE_DATABASE_URL")
        or request.config.getoption("--database-url")
    )

    if database_url is not None:
        return database_url

    # Get an open port to use for our PostgreSQL server
    port = _get_open_port()

    # Create a temporary directory to use as our data directory
    tmpdir = tempfile.mkdtemp()

    # Initial a database in our temporary directory
    subprocess.check_call(
        ["initdb", "-D", tmpdir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    proc = subprocess.Popen(
        ["postgres", "-D", tmpdir, "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Register a finalizer that will kill the started PostgreSQL server
    @request.addfinalizer
    def finalize():
        # Terminate the PostgreSQL process
        proc.send_signal(signal.SIGINT)
        proc.wait()

        # Remove the data directory
        shutil.rmtree(tmpdir, ignore_errors=True)

    for _ in range(5):
        try:
            conn = psycopg2.connect(
                database="postgres",
                host="localhost",
                port=port,
                connect_timeout=10,
            )
        except psycopg2.OperationalError:
            # Pause for a moment to give postgresql time to start
            time.sleep(1)
        else:
            # Set our isolation level
            conn.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
            )

            # Create a database for the warehouse tests
            cursor = conn.cursor()
            cursor.execute("CREATE DATABASE warehouse ENCODING 'UTF8'")

            # Commit our changes and close the connection
            cursor.close()
            conn.close()

            break
    else:
        raise RuntimeError("Could not start a PostgreSQL instance")

    return "postgresql://localhost:{}/warehouse".format(port)


@pytest.fixture(scope="session")
def database(postgresql):
    details = urllib.parse.urlparse(postgresql)

    # Ensure all extensions that we require are installed
    conn = psycopg2.connect(
        database=details.path[1:],
        host=details.hostname,
        port=details.port,
    )
    cursor = conn.cursor()
    cursor.execute("DROP SCHEMA public CASCADE")
    cursor.execute("CREATE SCHEMA public")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS citext")
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    conn.commit()
    cursor.close()
    conn.close()

    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option(
        "script_location",
        "warehouse:migrations",
    )
    alembic_cfg.set_main_option("url", postgresql)
    alembic.command.upgrade(alembic_cfg, "head")

    return postgresql


class FakeConnection:

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        pass

    def __getattr__(self, name):
        return getattr(self.connection, name)


class FakeEngine:

    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def begin(self):
        return FakeConnection(self.connection)

    def connect(self):
        return FakeConnection(self.connection)


@pytest.fixture
def engine(request, database):
    engine = sqlalchemy.create_engine(
        database,
        poolclass=sqlalchemy.pool.AssertionPool,
        isolation_level="SERIALIZABLE",
    )

    connection = engine.connect()
    transaction = connection.begin()

    @request.addfinalizer
    def finalize():
        transaction.rollback()
        connection.close()

    return FakeEngine(connection)


class ErrorRedis:

    def __init__(self, url):
        self.url = url

    @classmethod
    def from_url(cls, url):
        return ErrorRedis(url)

    def __getattr__(self, name):
        raise RuntimeError("Cannot access redis")


@pytest.fixture
def dbapp(database, engine):
    from warehouse.application import Warehouse

    return Warehouse.from_yaml(
        override={
            "database": {"url": database},
            "redis": {"downloads": "redis://nonexistant/0"},
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

    engine = pretend.stub(connect=connect)

    return Warehouse.from_yaml(
        override={
            "database": {"url": "postgresql:///nonexistant"},
            "redis": {"downloads": "redis://nonexistant/0"},
            "search": {"hosts": []},
        },
        engine=engine,
        redis_class=ErrorRedis,
    )
