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
import threading
import xmlrpc.client

from wsgiref.simple_server import make_server

import alembic.command
import click.testing
import pyramid.testing
import pytest
import webtest as _webtest

import bok_choy.browser

from bok_choy.browser import browser as _browser
from needle.driver import NeedleWebDriverMixin, NeedleOpera
from pytest_postgresql.factories import (
    init_postgresql_database, drop_postgresql_database, get_config,
)
from selenium.webdriver.edge.webdriver import WebDriver as MicrosoftEdge
from sqlalchemy import event

from warehouse.config import configure

from .common.db import Session


# Needle doesn't have a driver for Edge, so we'll have to create one now.
class NeedleMicrosoftEdge(NeedleWebDriverMixin, MicrosoftEdge):
    pass


# bok_choy needs to be told about some of these other kinds of browsers that
# it doesn't already know about.
# TODO: Contribute this back upstream.
bok_choy.browser.BROWSERS["MicrosoftEdge"] = NeedleMicrosoftEdge
bok_choy.browser.BROWSERS["opera"] = NeedleOpera


# We need to be able to pass the Sauce Labs tunnel identifier as a capability
# so that Sauce Labs can associate it with our test run. However, bok_choy
# doesn't expose a way of doing this, so we'll need to hack it in.
# TODO: Contribute this back upstream.
def __capabilities_dict(envs, tags):  # noqa
    caps = __capabilities_dict._real_implementation(envs, tags)
    if "SAUCELABS_TUNNEL" in os.environ:
        caps.setdefault("tunnelIdentifier", os.environ["SAUCELABS_TUNNEL"])
    return caps


__capabilities_dict._real_implementation = bok_choy.browser._capabilities_dict
bok_choy.browser._capabilities_dict = __capabilities_dict


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
    pg_host = config.get("host")
    pg_port = config.get("port") or 5432
    pg_user = config.get("user")
    pg_db = config.get("db", "tests")
    pg_version = config.get("version", 9.6)

    # Create our Database.
    init_postgresql_database(pg_user, pg_host, pg_port, pg_db)

    # Ensure our database gets deleted.
    @request.addfinalizer
    def drop_database():
        drop_postgresql_database(pg_user, pg_host, pg_port, pg_db, pg_version)

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
            "celery.scheduler_url": "redis://localhost:0/",
            "database.url": database,
            "docs.url": "http://docs.example.com/",
            "download_stats.url": "redis://localhost:0/",
            "ratelimit.url": "memory://",
            "elasticsearch.url": "https://localhost/warehouse",
            "files.backend": "warehouse.packaging.services.LocalFileStorage",
            "files.url": "http://localhost:7000/",
            "sessions.secret": "123456",
            "sessions.url": "redis://localhost:0/",
            "statuspage.url": "https://2p66nmmycsj3.statuspage.io",
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


class QueryRecorder(object):

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
    #       between test cases to wipe any commited changes.

    # We want to disable anything that relies on TLS here.
    app_config.add_settings(enforce_https=False)

    try:
        yield _TestApp(app_config.make_wsgi_app())
    finally:
        app_config.registry["sqlalchemy.engine"].dispose()


class LiveServerThread(threading.Thread):

    def __init__(self, app, *args, **kwargs):
        self.app = app
        self.is_ready = threading.Event()
        self.error = None
        super().__init__(*args, **kwargs)

    def run(self):
        try:
            self.httpd = make_server("localhost", 0, self.app)
            self.is_ready.set()
            self.httpd.serve_forever()
        except Exception as exc:
            self.error = exc
            self.is_ready.set()

    def terminate(self):
        if hasattr(self, "httpd"):
            # Stop the WSGI server
            self.httpd.shutdown()
            self.httpd.server_close()


@pytest.yield_fixture
def server_thread(app_config, webtest):
    # We need to allow unsafe-eval in our test suite, because otherwise we
    # cannot execute some javascript in the context of our page inside of our
    # selenium tests.
    app_config.get_settings()["csp"]["script-src"].append("'unsafe-eval'")

    # Spin up Warehouse in a thread
    _server_thread = LiveServerThread(webtest.app)
    _server_thread.daemon = True
    _server_thread.start()
    _server_thread.is_ready.wait()

    try:
        if _server_thread.error:
            raise _server_thread.error

        yield _server_thread
    finally:
        _server_thread.terminate()
        _server_thread.join()


@pytest.fixture
def server_url(pytestconfig, server_thread):
    hostname, port = server_thread.httpd.server_address
    if pytestconfig.option.liveserver_host:
        hostname = pytestconfig.option.liveserver_host

    return "http://{}:{}/".format(hostname, port)


@pytest.yield_fixture
def browser():
    selenium = _browser()

    # Opera currently doesn't support maximize_window()
    if selenium.desired_capabilities["browserName"] not in {"opera"}:
        selenium.maximize_window()

    try:
        yield selenium
    finally:
        selenium.quit()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # we only look at actual failing test calls, not setup/teardown
    if rep.when == "call" and rep.failed:
        if "browser" in item.fixturenames:
            browser = item.funcargs["browser"]
            for log_type in (set(browser.log_types) - {"har"}):
                data = "\n\n".join(
                    filter(
                        None,
                        (l.get("message") for l in browser.get_log(log_type)))
                )
                if data:
                    rep.sections.append(
                        ("Captured {} log".format(log_type), data)
                    )


def pytest_addoption(parser):
    parser.addoption("--liveserver-host", dest="liveserver_host")
