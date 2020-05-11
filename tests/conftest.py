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
import os.path
import xmlrpc.client

from contextlib import contextmanager
from unittest import mock

import alembic.command
import click.testing
import pretend
import pyramid.testing
import pytest
import webtest as _webtest

from pyramid.i18n import TranslationString
from pyramid.static import ManifestCacheBuster
from pytest_postgresql.factories import DatabaseJanitor, get_config
from sqlalchemy import event

from warehouse import admin, config, static
from warehouse.accounts import services as account_services
from warehouse.macaroons import services as macaroon_services
from warehouse.metrics import IMetricsService

from .common.db import Session


def pytest_collection_modifyitems(items):
    for item in items:
        if not hasattr(item, "module"):  # e.g.: DoctestTextfile
            continue

        module_path = os.path.relpath(
            item.module.__file__, os.path.commonprefix([__file__, item.module.__file__])
        )

        module_root_dir = module_path.split(os.pathsep)[0]
        if module_root_dir.startswith("functional"):
            item.add_marker(pytest.mark.functional)
        elif module_root_dir.startswith("unit"):
            item.add_marker(pytest.mark.unit)
        else:
            raise RuntimeError("Unknown test type (filename = {0})".format(module_path))


@contextmanager
def metrics_timing(*args, **kwargs):
    yield None


@pytest.fixture
def metrics():
    return pretend.stub(
        event=pretend.call_recorder(lambda *args, **kwargs: None),
        increment=pretend.call_recorder(lambda *args, **kwargs: None),
        histogram=pretend.call_recorder(lambda *args, **kwargs: None),
        timing=pretend.call_recorder(lambda *args, **kwargs: None),
        timed=pretend.call_recorder(
            lambda *args, **kwargs: metrics_timing(*args, **kwargs)
        ),
    )


class _Services:
    def __init__(self):
        self._services = {}

    def register_service(self, iface, context, service_obj):
        self._services[(iface, context)] = service_obj

    def find_service(self, iface, context):
        return self._services[(iface, context)]


@pytest.fixture
def pyramid_services(metrics):
    services = _Services()

    # Register our global services.
    services.register_service(IMetricsService, None, metrics)

    return services


@pytest.fixture
def pyramid_request(pyramid_services):
    dummy_request = pyramid.testing.DummyRequest()
    dummy_request.find_service = pyramid_services.find_service

    def localize(message, **kwargs):
        ts = TranslationString(message, **kwargs)
        return ts.interpolate()

    dummy_request._ = localize

    return dummy_request


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
    pg_host = config.get("host")
    pg_port = config.get("port") or os.environ.get("PGPORT", 5432)
    pg_user = config.get("user")
    pg_db = config.get("db", "tests")
    pg_version = config.get("version", 10.1)

    janitor = DatabaseJanitor(pg_user, pg_host, pg_port, pg_db, pg_version)

    # In case the database already exists, possibly due to an aborted test run,
    # attempt to drop it before creating
    janitor.drop()

    # Create our Database.
    janitor.init()

    # Ensure our database gets deleted.
    @request.addfinalizer
    def drop_database():
        janitor.drop()

    return "postgresql://{}@{}:{}/{}".format(pg_user, pg_host, pg_port, pg_db)


class MockManifestCacheBuster(ManifestCacheBuster):
    def __init__(self, *args, strict=True, **kwargs):
        super().__init__(*args, **kwargs)

    def get_manifest(self):
        return {}


@pytest.fixture
def mock_manifest_cache_buster():
    return MockManifestCacheBuster


@pytest.fixture(scope="session")
def app_config(database):
    settings = {
        "warehouse.prevent_esi": True,
        "warehouse.token": "insecure token",
        "camo.url": "http://localhost:9000/",
        "camo.key": "insecure key",
        "celery.broker_url": "amqp://",
        "celery.result_url": "redis://localhost:0/",
        "celery.scheduler_url": "redis://localhost:0/",
        "database.url": database,
        "docs.url": "http://docs.example.com/",
        "ratelimit.url": "memory://",
        "elasticsearch.url": "https://localhost/warehouse",
        "files.backend": "warehouse.packaging.services.LocalFileStorage",
        "docs.backend": "warehouse.packaging.services.LocalFileStorage",
        "mail.backend": "warehouse.email.services.SMTPEmailSender",
        "malware_check.backend": (
            "warehouse.malware.services.PrinterMalwareCheckService"
        ),
        "files.url": "http://localhost:7000/",
        "sessions.secret": "123456",
        "sessions.url": "redis://localhost:0/",
        "statuspage.url": "https://2p66nmmycsj3.statuspage.io",
        "warehouse.xmlrpc.cache.url": "redis://localhost:0/",
    }
    with mock.patch.object(config, "ManifestCacheBuster", MockManifestCacheBuster):
        with mock.patch("warehouse.admin.ManifestCacheBuster", MockManifestCacheBuster):
            with mock.patch.object(static, "whitenoise_add_manifest"):
                cfg = config.configure(settings=settings)

    # Ensure our migrations have been ran.
    alembic.command.upgrade(cfg.alembic_config(), "head")

    return cfg


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


@pytest.yield_fixture
def user_service(db_session, metrics):
    return account_services.DatabaseUserService(db_session, metrics=metrics)


@pytest.yield_fixture
def macaroon_service(db_session):
    return macaroon_services.DatabaseMacaroonService(db_session)


@pytest.yield_fixture
def token_service(app_config):
    return account_services.TokenService(secret="secret", salt="salt", max_age=21600)


class QueryRecorder:
    def __init__(self):
        self.queries = []
        self.recording = False

    def __enter__(self):
        self.start()

    def __exit__(self, type, value, traceback):
        self.stop()

    def record(self, conn, cursor, statement, *args):
        if self.recording:
            self.queries.append(statement)

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False

    def clear(self):
        self.queries = []


@pytest.yield_fixture
def query_recorder(app_config):
    recorder = QueryRecorder()

    engine = app_config.registry["sqlalchemy.engine"]
    event.listen(engine, "before_cursor_execute", recorder.record)

    try:
        yield recorder
    finally:
        event.remove(engine, "before_cursor_execute", recorder.record)


@pytest.fixture
def db_request(pyramid_request, db_session):
    pyramid_request.db = db_session
    pyramid_request.flags = admin.flags.Flags(pyramid_request)
    return pyramid_request


class _TestApp(_webtest.TestApp):
    def xmlrpc(self, path, method, *args):
        body = xmlrpc.client.dumps(args, methodname=method)
        resp = self.post(path, body, headers={"Content-Type": "text/xml"})
        return xmlrpc.client.loads(resp.body)


@pytest.yield_fixture
def webtest(app_config):
    # TODO: Ensure that we have per test isolation of the database level
    #       changes. This probably involves flushing the database or something
    #       between test cases to wipe any committed changes.

    # We want to disable anything that relies on TLS here.
    app_config.add_settings(enforce_https=False)

    try:
        yield _TestApp(app_config.make_wsgi_app())
    finally:
        app_config.registry["sqlalchemy.engine"].dispose()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # we only look at actual failing test calls, not setup/teardown
    if rep.when == "call" and rep.failed:
        if "browser" in item.fixturenames:
            browser = item.funcargs["browser"]
            for log_type in set(browser.log_types) - {"har"}:
                data = "\n\n".join(
                    filter(
                        None, (log.get("message") for log in browser.get_log(log_type))
                    )
                )
                if data:
                    rep.sections.append(("Captured {} log".format(log_type), data))


@pytest.fixture(scope="session")
def monkeypatch_session():
    # NOTE: This is a minor hack to avoid duplicate monkeypatching
    # on every function scope for dummy_localize.
    # https://github.com/pytest-dev/pytest/issues/1872#issuecomment-375108891
    from _pytest.monkeypatch import MonkeyPatch

    m = MonkeyPatch()
    yield m
    m.undo()
