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

import os.path
import xmlrpc.client

import alembic.command
import click.testing
import psycopg2
import pyramid.testing
import pytest
import webtest as _webtest

from pytest_dbfixtures.factories.postgresql import (
    init_postgresql_database, drop_postgresql_database,
)
from pytest_dbfixtures.utils import get_config
from sqlalchemy import event

from warehouse.config import configure

from .common.db import Session


def pytest_collection_modifyitems(items):
    for item in items:
        if not hasattr(item, "module"):  # e.g.: DoctestTextfile
            continue

        module_path = os.path.relpath(
            item.module.__file__,
            os.path.commonprefix([__file__, item.module.__file__]),
        )

        module_root_dir = module_path.split(os.pathsep)[0]
        if (module_root_dir.startswith("functional")):
            item.add_marker(pytest.mark.functional)
        elif module_root_dir.startswith("unit"):
            item.add_marker(pytest.mark.unit)
        else:
            raise RuntimeError(
                "Unknown test type (filename = {0})".format(module_path)
            )


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
def database(request):
    config = get_config(request)
    pg_host = config.postgresql.host
    pg_port = config.postgresql.port
    pg_user = config.postgresql.user
    pg_db = config.postgresql.db

    # Create our Database.
    init_postgresql_database(psycopg2, pg_user, pg_host, pg_port, pg_db)

    # Ensure our database gets deleted.
    @request.addfinalizer
    def drop_database():
        drop_postgresql_database(psycopg2, pg_user, pg_host, pg_port, pg_db)

    return "postgresql://{}@{}:{}/{}".format(pg_user, pg_host, pg_port, pg_db)


@pytest.fixture
def app_config(database):
    config = configure(
        settings={
            "warehouse.prevent_esi": True,
            "warehouse.token": "insecure token",
            "camo.url": "http://localhost:9000/",
            "camo.key": "insecure key",
            "celery.broker_url": "amqp://",
            "celery.result_url": "redis://localhost:0/",
            "database.url": database,
            "docs.url": "http://docs.example.com/",
            "download_stats.url": "redis://localhost:0/",
            "elasticsearch.url": "https://localhost/warehouse",
            "files.backend": "warehouse.packaging.services.LocalFileStorage",
            "sessions.secret": "123456",
            "sessions.url": "redis://localhost:0/",
        },
    )

    # Ensure our migrations have been ran.
    alembic.command.upgrade(config.alembic_config(), "head")

    return config


@pytest.yield_fixture
def db_session(app_config):
    engine = app_config.registry["sqlalchemy.engine"]
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)

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
        Session.remove()
        trans.rollback()
        conn.close()
        engine.dispose()


@pytest.fixture
def db_request(pyramid_request, db_session):
    pyramid_request.db = db_session
    return pyramid_request


class _TestApp(_webtest.TestApp):

    def xmlrpc(self, path, method, *args):
        body = xmlrpc.client.dumps(args, methodname=method)
        resp = self.post(path, body, headers={"Content-Type": "text/xml"})
        return xmlrpc.client.loads(resp.body)


@pytest.yield_fixture
def webtest(app_config):
    # We want to disable anything that relies on TLS here.
    app_config.add_settings(enforce_https=False)

    try:
        yield _TestApp(app_config.make_wsgi_app())
    finally:
        app_config.registry["sqlalchemy.engine"].dispose()
