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
import re
import xmlrpc.client

from collections import defaultdict
from contextlib import contextmanager
from unittest import mock

import alembic.command
import click.testing
import pretend
import pyramid.testing
import pytest
import stripe
import webtest as _webtest

from jinja2 import Environment, FileSystemLoader
from psycopg2.errors import InvalidCatalogName
from pyramid.i18n import TranslationString
from pyramid.static import ManifestCacheBuster
from pyramid_jinja2 import IJinja2Environment
from pyramid_mailer.mailer import DummyMailer
from pytest_postgresql.config import get_config
from pytest_postgresql.janitor import DatabaseJanitor
from sqlalchemy import event

import warehouse

from warehouse import admin, config, email, static
from warehouse.accounts import services as account_services
from warehouse.accounts.interfaces import ITokenService, IUserService
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.email import services as email_services
from warehouse.email.interfaces import IEmailSender
from warehouse.macaroons import services as macaroon_services
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService
from warehouse.oidc import services as oidc_services
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.utils import GITHUB_OIDC_ISSUER_URL
from warehouse.organizations import services as organization_services
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.packaging import services as packaging_services
from warehouse.packaging.interfaces import IProjectService
from warehouse.subscriptions import services as subscription_services
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService

from .common.db import Session
from .common.db.accounts import EmailFactory, UserFactory
from .common.db.ip_addresses import IpAddressFactory


@contextmanager
def metrics_timing(*args, **kwargs):
    yield None


@pytest.fixture
def metrics():
    return pretend.stub(
        event=pretend.call_recorder(lambda *args, **kwargs: None),
        gauge=pretend.call_recorder(lambda *args, **kwargs: None),
        increment=pretend.call_recorder(lambda *args, **kwargs: None),
        histogram=pretend.call_recorder(lambda *args, **kwargs: None),
        timing=pretend.call_recorder(lambda *args, **kwargs: None),
        timed=pretend.call_recorder(
            lambda *args, **kwargs: metrics_timing(*args, **kwargs)
        ),
    )


@pytest.fixture
def remote_addr():
    return "1.2.3.4"


@pytest.fixture
def remote_addr_hashed():
    """
    Static output of `hashlib.sha256(remote_addr.encode("utf8")).hexdigest()`
    Created statically to prevent needing to calculate it every run.
    """
    return "6694f83c9f476da31f5df6bcc520034e7e57d421d247b9d34f49edbfc84a764c"


@pytest.fixture
def remote_addr_salted():
    """
    Output of `hashlib.sha256((remote_addr + "pepa").encode("utf8")).hexdigest()`
    """
    return "a69a49383d81404e4b1df297c7baa28e1cd6c4ee1495ed5d0ab165a63a147763"


@pytest.fixture
def jinja():
    dir_name = os.path.join(os.path.dirname(warehouse.__file__))

    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
        ],
        cache_size=0,
    )

    return env


class _Services:
    def __init__(self):
        self._services = defaultdict(lambda: defaultdict(dict))

    def register_service(self, service_obj, iface=None, context=None, name=""):
        self._services[iface][context][name] = service_obj

    def find_service(self, iface=None, context=None, name=""):
        return self._services[iface][context][name]


@pytest.fixture
def pyramid_services(
    billing_service,
    email_service,
    metrics,
    organization_service,
    subscription_service,
    token_service,
    user_service,
    project_service,
    oidc_service,
    macaroon_service,
):
    services = _Services()

    # Register our global services.
    services.register_service(billing_service, IBillingService, None, name="")
    services.register_service(email_service, IEmailSender, None, name="")
    services.register_service(metrics, IMetricsService, None, name="")
    services.register_service(organization_service, IOrganizationService, None, name="")
    services.register_service(subscription_service, ISubscriptionService, None, name="")
    services.register_service(token_service, ITokenService, None, name="password")
    services.register_service(token_service, ITokenService, None, name="email")
    services.register_service(user_service, IUserService, None, name="")
    services.register_service(project_service, IProjectService, None, name="")
    services.register_service(oidc_service, IOIDCPublisherService, None, name="github")
    services.register_service(macaroon_service, IMacaroonService, None, name="")

    return services


@pytest.fixture
def pyramid_request(pyramid_services, jinja, remote_addr, remote_addr_hashed):
    pyramid.testing.setUp()
    dummy_request = pyramid.testing.DummyRequest()
    dummy_request.find_service = pyramid_services.find_service
    dummy_request.remote_addr = remote_addr
    dummy_request.remote_addr_hashed = remote_addr_hashed
    dummy_request.authentication_method = pretend.stub()
    dummy_request._unauthenticated_userid = None
    dummy_request.oidc_publisher = None

    dummy_request.registry.registerUtility(jinja, IJinja2Environment, name=".jinja2")

    dummy_request._task_stub = pretend.stub(
        delay=pretend.call_recorder(lambda *a, **kw: None)
    )
    dummy_request.task = pretend.call_recorder(
        lambda *a, **kw: dummy_request._task_stub
    )

    def localize(message, **kwargs):
        ts = TranslationString(message, **kwargs)
        return ts.interpolate()

    dummy_request._ = localize

    yield dummy_request

    pyramid.testing.tearDown()


@pytest.fixture
def pyramid_config(pyramid_request):
    with pyramid.testing.testConfig(request=pyramid_request) as config:
        yield config


@pytest.fixture
def pyramid_user(pyramid_request):
    user = UserFactory.create()
    EmailFactory.create(user=user, verified=True)
    pyramid_request.user = user
    return user


@pytest.fixture
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
    pg_version = config.get("version", 14.4)

    janitor = DatabaseJanitor(pg_user, pg_host, pg_port, pg_db, pg_version)

    # In case the database already exists, possibly due to an aborted test run,
    # attempt to drop it before creating
    try:
        janitor.drop()
    except InvalidCatalogName:
        # We can safely ignore this exception as that means there was
        # no leftover database
        pass

    # Create our Database.
    janitor.init()

    # Ensure our database gets deleted.
    @request.addfinalizer
    def drop_database():
        janitor.drop()

    return f"postgresql://{pg_user}@{pg_host}:{pg_port}/{pg_db}"


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
        "warehouse.ip_salt": "insecure salt",
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
        "archive_files.backend": "warehouse.packaging.services.LocalArchiveFileStorage",
        "simple.backend": "warehouse.packaging.services.LocalSimpleStorage",
        "docs.backend": "warehouse.packaging.services.LocalDocsStorage",
        "sponsorlogos.backend": "warehouse.admin.services.LocalSponsorLogoStorage",
        "billing.backend": "warehouse.subscriptions.services.MockStripeBillingService",
        "mail.backend": "warehouse.email.services.SMTPEmailSender",
        "files.url": "http://localhost:7000/",
        "archive_files.url": "http://localhost:7000/archive",
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


@pytest.fixture
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
def user_service(db_session, metrics, remote_addr):
    return account_services.DatabaseUserService(
        db_session, metrics=metrics, remote_addr=remote_addr
    )


@pytest.fixture
def project_service(db_session, metrics, ratelimiters=None):
    return packaging_services.ProjectService(
        db_session, metrics, ratelimiters=ratelimiters
    )


@pytest.fixture
def oidc_service(db_session):
    # We pretend to be a verifier for GitHub OIDC JWTs, for the purposes of testing.
    return oidc_services.NullOIDCPublisherService(
        db_session,
        pretend.stub(),
        GITHUB_OIDC_ISSUER_URL,
        pretend.stub(),
        pretend.stub(),
        pretend.stub(),
    )


@pytest.fixture
def macaroon_service(db_session):
    return macaroon_services.DatabaseMacaroonService(db_session)


@pytest.fixture
def organization_service(db_session):
    return organization_services.DatabaseOrganizationService(db_session)


@pytest.fixture
def billing_service(app_config):
    stripe.api_base = app_config.registry.settings["billing.api_base"]
    stripe.api_version = app_config.registry.settings["billing.api_version"]
    stripe.api_key = "sk_test_123"
    return subscription_services.MockStripeBillingService(
        api=stripe,
        publishable_key="pk_test_123",
        webhook_secret="whsec_123",
    )


@pytest.fixture
def subscription_service(db_session):
    return subscription_services.StripeSubscriptionService(db_session)


@pytest.fixture
def token_service(app_config):
    return account_services.TokenService(secret="secret", salt="salt", max_age=21600)


@pytest.fixture
def email_service():
    return email_services.SMTPEmailSender(
        mailer=DummyMailer(), sender="noreply@pypi.dev"
    )


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


@pytest.fixture
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
    pyramid_request.banned = admin.bans.Bans(pyramid_request)
    pyramid_request.organization_access = True
    pyramid_request.ip_address = IpAddressFactory.create(
        ip_address=pyramid_request.remote_addr,
        hashed_ip_address=pyramid_request.remote_addr_hashed,
    )
    return pyramid_request


@pytest.fixture
def enable_organizations(db_request):
    flag = db_request.db.get(AdminFlag, AdminFlagValue.DISABLE_ORGANIZATIONS.value)
    flag.enabled = False
    yield
    flag.enabled = True


@pytest.fixture
def send_email(pyramid_request, monkeypatch):
    send_email_stub = pretend.stub(
        delay=pretend.call_recorder(lambda *args, **kwargs: None)
    )
    pyramid_request.task = pretend.call_recorder(
        lambda *args, **kwargs: send_email_stub
    )
    pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}
    monkeypatch.setattr(email, "send_email", send_email_stub)
    return send_email_stub


@pytest.fixture
def make_email_renderers(pyramid_config):
    def _make_email_renderers(
        name,
        subject="Email Subject",
        body="Email Body",
        html="Email HTML Body",
    ):
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/{name}/subject.txt"
        )
        subject_renderer.string_response = subject
        body_renderer = pyramid_config.testing_add_renderer(f"email/{name}/body.txt")
        body_renderer.string_response = body
        html_renderer = pyramid_config.testing_add_renderer(f"email/{name}/body.html")
        html_renderer.string_response = html
        return subject_renderer, body_renderer, html_renderer

    return _make_email_renderers


class _TestApp(_webtest.TestApp):
    def xmlrpc(self, path, method, *args):
        body = xmlrpc.client.dumps(args, methodname=method)
        resp = self.post(path, body, headers={"Content-Type": "text/xml"})
        return xmlrpc.client.loads(resp.body)


@pytest.fixture
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


@pytest.fixture(scope="session")
def monkeypatch_session():
    # NOTE: This is a minor hack to avoid duplicate monkeypatching
    # on every function scope for dummy_localize.
    # https://github.com/pytest-dev/pytest/issues/1872#issuecomment-375108891
    from _pytest.monkeypatch import MonkeyPatch

    m = MonkeyPatch()
    yield m
    m.undo()


class _MockRedis:
    """
    Just enough Redis for our tests.
    In-memory only, no persistence.
    Does NOT implement the full Redis API.
    """

    def __init__(self, cache=None):
        self.cache = cache

        if not self.cache:
            self.cache = dict()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def delete(self, key):
        del self.cache[key]

    def execute(self):
        pass

    def exists(self, key):
        return key in self.cache

    def expire(self, _key, _seconds):
        pass

    def from_url(self, _url):
        return self

    def hget(self, hash_, key):
        try:
            return self.cache[hash_][key]
        except KeyError:
            return None

    def hset(self, hash_, key, value, *_args, **_kwargs):
        if hash_ not in self.cache:
            self.cache[hash_] = dict()
        self.cache[hash_][key] = value

    def get(self, key):
        return self.cache.get(key)

    def pipeline(self):
        return self

    def scan_iter(self, search, count):
        del count  # unused
        return [key for key in self.cache.keys() if re.search(search, key)]

    def set(self, key, value):
        self.cache[key] = value

    def setex(self, key, value, _seconds):
        self.cache[key] = value


@pytest.fixture
def mockredis():
    mock_redis = _MockRedis()
    yield mock_redis
