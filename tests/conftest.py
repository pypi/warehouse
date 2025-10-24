# SPDX-License-Identifier: Apache-2.0

import os
import os.path
import re
import xmlrpc.client

from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import alembic.command
import click.testing
import pretend
import pyramid.testing
import pytest
import stripe
import transaction
import webtest as _webtest

from jinja2 import Environment, FileSystemLoader
from psycopg.errors import InvalidCatalogName
from pypi_attestations import Attestation, Envelope, Provenance, VerificationMaterial
from pyramid.i18n import TranslationString
from pyramid.static import ManifestCacheBuster
from pyramid_jinja2 import IJinja2Environment
from pyramid_mailer.mailer import DummyMailer
from pytest_postgresql.config import get_config
from pytest_postgresql.janitor import DatabaseJanitor
from sqlalchemy import event

import warehouse

from warehouse import admin, config, static
from warehouse.accounts import services as account_services
from warehouse.accounts.interfaces import (
    IDomainStatusService,
    ITokenService,
    IUserService,
)
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.attestations import services as attestations_services
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.cache import services as cache_services
from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.email import services as email_services
from warehouse.email.interfaces import IEmailSender
from warehouse.helpdesk import services as helpdesk_services
from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService
from warehouse.macaroons import services as macaroon_services
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService
from warehouse.oidc import services as oidc_services
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.utils import ACTIVESTATE_OIDC_ISSUER_URL, GITHUB_OIDC_ISSUER_URL
from warehouse.organizations import services as organization_services
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.packaging import services as packaging_services
from warehouse.packaging.interfaces import IProjectService
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter
from warehouse.search import services as search_services
from warehouse.search.interfaces import ISearchService
from warehouse.subscriptions import services as subscription_services
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService

from .common.constants import REMOTE_ADDR, REMOTE_ADDR_HASHED
from .common.db import Session
from .common.db.accounts import EmailFactory, UserFactory
from .common.db.ip_addresses import IpAddressFactory

_HERE = Path(__file__).parent.resolve()
_FIXTURES = _HERE / "_fixtures"


@contextmanager
def metrics_timing(*args, **kwargs):
    yield None


def _event(
    title,
    text,
    alert_type=None,
    aggregation_key=None,
    source_type_name=None,
    date_happened=None,
    priority=None,
    tags=None,
    hostname=None,
):
    return None  # pragma: no cover


@pytest.fixture
def metrics():
    """
    A good-enough fake metrics fixture.
    """
    return pretend.stub(
        event=pretend.call_recorder(lambda *args, **kwargs: _event(*args, **kwargs)),
        gauge=pretend.call_recorder(
            lambda metric, value, tags=None, sample_rate=1: None
        ),
        increment=pretend.call_recorder(
            lambda metric, value=1, tags=None, sample_rate=1: None
        ),
        histogram=pretend.call_recorder(
            lambda metric, value, tags=None, sample_rate=1: None
        ),
        timing=pretend.call_recorder(
            lambda metric, value, tags=None, sample_rate=1: None
        ),
        timed=pretend.call_recorder(
            lambda metric=None, tags=None, sample_rate=1, use_ms=None: metrics_timing(
                metric=metric, tags=tags, sample_rate=sample_rate, use_ms=use_ms
            )
        ),
    )


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
    github_oidc_service,
    activestate_oidc_service,
    integrity_service,
    macaroon_service,
    helpdesk_service,
    notification_service,
    query_results_cache_service,
    search_service,
    domain_status_service,
    ratelimit_service,
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
    services.register_service(
        github_oidc_service, IOIDCPublisherService, None, name="github"
    )
    services.register_service(
        activestate_oidc_service, IOIDCPublisherService, None, name="activestate"
    )
    services.register_service(integrity_service, IIntegrityService, None)
    services.register_service(macaroon_service, IMacaroonService, None, name="")
    services.register_service(helpdesk_service, IHelpDeskService, None)
    services.register_service(notification_service, IAdminNotificationService)
    services.register_service(query_results_cache_service, IQueryResultsCache)
    services.register_service(search_service, ISearchService)
    services.register_service(domain_status_service, IDomainStatusService)
    services.register_service(ratelimit_service, IRateLimiter, name="email.add")
    services.register_service(ratelimit_service, IRateLimiter, name="email.verify")

    return services


@pytest.fixture
def pyramid_request(pyramid_services, jinja):
    pyramid.testing.setUp()
    dummy_request = pyramid.testing.DummyRequest()
    dummy_request.find_service = pyramid_services.find_service
    dummy_request.remote_addr = REMOTE_ADDR
    dummy_request.remote_addr_hashed = REMOTE_ADDR_HASHED
    dummy_request.authentication_method = pretend.stub()
    dummy_request._unauthenticated_userid = None
    dummy_request.user = None
    dummy_request.oidc_publisher = None
    dummy_request.metrics = dummy_request.find_service(IMetricsService)

    dummy_request.registry.registerUtility(jinja, IJinja2Environment, name=".jinja2")

    dummy_request._task_stub = pretend.stub(
        delay=pretend.call_recorder(lambda *a, **kw: None)
    )
    dummy_request.task = pretend.call_recorder(
        lambda *a, **kw: dummy_request._task_stub
    )
    dummy_request.log = pretend.stub(
        bind=pretend.call_recorder(lambda *args, **kwargs: dummy_request.log),
        info=pretend.call_recorder(lambda *args, **kwargs: None),
        warning=pretend.call_recorder(lambda *args, **kwargs: None),
        error=pretend.call_recorder(lambda *args, **kwargs: None),
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
def database(request, worker_id):
    config = get_config(request)
    pg_host = config.get("host")
    pg_port = config.get("port") or os.environ.get("PGPORT", 5432)
    pg_user = config.get("user")
    pg_db = f"tests-{worker_id}"
    pg_version = config.get("version", 16.1)

    janitor = DatabaseJanitor(
        user=pg_user,
        host=pg_host,
        port=pg_port,
        dbname=pg_db,
        version=pg_version,
    )

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

    return f"postgresql+psycopg://{pg_user}@{pg_host}:{pg_port}/{pg_db}"


class MockManifestCacheBuster(ManifestCacheBuster):
    def __init__(self, *args, strict=True, **kwargs):
        super().__init__(*args, **kwargs)

    def get_manifest(self):
        return {}


@pytest.fixture
def mock_manifest_cache_buster():
    return MockManifestCacheBuster


def get_app_config(database, nondefaults=None):
    settings = {
        "warehouse.prevent_esi": True,
        "warehouse.token": "insecure token",
        "warehouse.ip_salt": "insecure salt",
        "camo.url": "http://localhost:9000/",
        "camo.key": "insecure key",
        "celery.broker_redis_url": "redis://localhost:0/",
        "celery.result_url": "redis://localhost:0/",
        "celery.scheduler_url": "redis://localhost:0/",
        "database.url": database,
        "docs.url": "http://docs.example.com/",
        "ratelimit.url": "memory://",
        "db_results_cache.url": "redis://cache:0/",
        "opensearch.url": "https://localhost/warehouse",
        "files.backend": "warehouse.packaging.services.LocalFileStorage",
        "archive_files.backend": "warehouse.packaging.services.LocalArchiveFileStorage",
        "archive_files.path": "/tmp",
        "simple.backend": "warehouse.packaging.services.LocalSimpleStorage",
        "docs.backend": "warehouse.packaging.services.LocalDocsStorage",
        "sponsorlogos.backend": "warehouse.admin.services.LocalSponsorLogoStorage",
        "billing.backend": "warehouse.subscriptions.services.MockStripeBillingService",
        "integrity.backend": "warehouse.attestations.services.NullIntegrityService",
        "billing.api_base": "http://stripe:12111",
        "billing.api_version": "2020-08-27",
        "mail.backend": "warehouse.email.services.SMTPEmailSender",
        "helpdesk.backend": "warehouse.helpdesk.services.ConsoleHelpDeskService",
        "helpdesk.notification_backend": "warehouse.helpdesk.services.ConsoleAdminNotificationService",  # noqa: E501
        "files.url": "http://localhost:7000/",
        "archive_files.url": "http://localhost:7000/archive",
        "sessions.secret": "123456",
        "sessions.url": "redis://localhost:0/",
        "statuspage.url": "https://2p66nmmycsj3.statuspage.io",
        "warehouse.xmlrpc.cache.url": "redis://localhost:0/",
        "terms.revision": "initial",
        "oidc.jwk_cache_url": "redis://localhost:0/",
        "warehouse.oidc.audience": "pypi",
        "oidc.backend": "warehouse.oidc.services.NullOIDCPublisherService",
        "captcha.backend": "warehouse.captcha.hcaptcha.Service",
    }

    if nondefaults:
        settings.update(nondefaults)

    with mock.patch.object(config, "ManifestCacheBuster", MockManifestCacheBuster):
        with mock.patch("warehouse.admin.ManifestCacheBuster", MockManifestCacheBuster):
            with mock.patch.object(static, "whitenoise_add_manifest"):
                cfg = config.configure(settings=settings)

    # Run migrations:
    # This might harmlessly run multiple times if there are several app config fixtures
    # in the test session, using the same database.
    alembic.command.upgrade(cfg.alembic_config(), "head")

    return cfg


@contextmanager
def get_db_session_for_app_config(app_config):
    """
    Refactor: This helper function is designed to help fixtures yield a database
    session for a particular app_config.

    It needs the app_config in order to fetch the database engine that's owned
    by the config.
    """

    # TODO: We possibly accept 2 instances of the sqlalchemy engine.
    # There's a bit of circular dependencies in place:
    # 1) To create a database session, we need to create an app config registry
    #    and read config.registry["sqlalchemy.engine"]
    # 2) To create an app config registry, we need to be able to dictate the
    #    database session through the initial config.
    #
    # 1) and 2) clash.
    engine = app_config.registry["sqlalchemy.engine"]  # get_sqlalchemy_engine(database)
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        Session.remove()
        trans.rollback()
        conn.close()
        engine.dispose()


@pytest.fixture(scope="session")
def app_config(database):
    return get_app_config(database)


@pytest.fixture(scope="session")
def app_config_dbsession_from_env(database):
    nondefaults = {
        "warehouse.db_create_session": lambda r: r.environ.get("warehouse.db_session"),
        "breached_passwords.backend": "warehouse.accounts.services.NullPasswordBreachedService",  # noqa: E501
        "token.two_factor.secret": "insecure token",
        # A running redis-like service is required for functional web sessions
        "sessions.url": "redis://cache:0/",
    }

    return get_app_config(database, nondefaults)


@pytest.fixture
def db_session(app_config):
    """
    Refactor:

    This fixture actually manages a specific app_config paired with a database
    connection. For this reason, it's suggested to change the name to
    db_and_app, and yield both app_config and db_session.
    """
    with get_db_session_for_app_config(app_config) as _db_session:
        yield _db_session


@pytest.fixture
def user_service(db_session, metrics):
    return account_services.DatabaseUserService(
        db_session, metrics=metrics, remote_addr=REMOTE_ADDR
    )


@pytest.fixture
def project_service(db_session, metrics, ratelimiters=None):
    return packaging_services.ProjectService(
        db_session, metrics, ratelimiters=ratelimiters
    )


@pytest.fixture
def github_oidc_service(db_session):
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
def activestate_oidc_service(db_session):
    # We pretend to be a verifier for GitHub OIDC JWTs, for the purposes of testing.
    return oidc_services.NullOIDCPublisherService(
        db_session,
        pretend.stub(),
        ACTIVESTATE_OIDC_ISSUER_URL,
        pretend.stub(),
        pretend.stub(),
        pretend.stub(),
    )


@pytest.fixture
def dummy_attestation():
    return Attestation(
        version=1,
        verification_material=VerificationMaterial(
            certificate="somebase64string", transparency_entries=[dict()]
        ),
        envelope=Envelope(
            statement="somebase64string",
            signature="somebase64string",
        ),
    )


@pytest.fixture
def integrity_service(db_session):
    return attestations_services.NullIntegrityService(db_session)


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
        domain="localhost",
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


@pytest.fixture
def helpdesk_service():
    return helpdesk_services.ConsoleHelpDeskService()


@pytest.fixture
def notification_service():
    return helpdesk_services.ConsoleAdminNotificationService()


@pytest.fixture
def query_results_cache_service(mockredis):
    return cache_services.RedisQueryResults(redis_client=mockredis)


@pytest.fixture
def search_service():
    return search_services.NullSearchService()


@pytest.fixture
def domain_status_service(mocker):
    service = account_services.NullDomainStatusService()
    mocker.spy(service, "get_domain_status")
    return service


@pytest.fixture
def ratelimit_service(mocker):
    service = DummyRateLimiter()
    mocker.spy(service, "clear")
    return service


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
        recorder.clear()


@pytest.fixture
def db_request(pyramid_request, db_session, tm):
    pyramid_request.db = db_session
    pyramid_request.tm = tm
    pyramid_request.flags = admin.flags.Flags(pyramid_request)
    pyramid_request.banned = admin.bans.Bans(pyramid_request)
    pyramid_request.organization_access = True
    pyramid_request.ip_address = IpAddressFactory.create(
        ip_address=pyramid_request.remote_addr,
        hashed_ip_address=pyramid_request.remote_addr_hashed,
    )
    return pyramid_request


@pytest.fixture
def _enable_all_oidc_providers(webtest):
    flags = (
        AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
        AdminFlagValue.DISALLOW_GITLAB_OIDC,
        AdminFlagValue.DISALLOW_GITHUB_OIDC,
        AdminFlagValue.DISALLOW_GOOGLE_OIDC,
    )
    original_flag_values = {}
    db_sess = webtest.extra_environ["warehouse.db_session"]

    for flag in flags:
        flag_db = db_sess.get(AdminFlag, flag.value)
        original_flag_values[flag] = flag_db.enabled
        flag_db.enabled = False
    yield

    for flag in flags:
        flag_db = db_sess.get(AdminFlag, flag.value)
        flag_db.enabled = original_flag_values[flag]


@pytest.fixture
def _enable_organizations(db_request):
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
    monkeypatch.setattr(warehouse.email, "send_email", send_email_stub)
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
def tm():
    # Create a new transaction manager for dependant test cases
    tm = transaction.TransactionManager(explicit=True)
    tm.begin()

    yield tm

    # Abort the transaction, leaving database in previous state
    tm.abort()


@pytest.fixture
def webtest(app_config_dbsession_from_env, tm):
    """
    This fixture yields a test app with an alternative Pyramid configuration,
    injecting the database session and transaction manager into the app.

    This is because the Warehouse app normally manages its own database session.

    After the fixture has yielded the app, the transaction is rolled back and
    the database is left in its previous state.
    """

    # We want to disable anything that relies on TLS here.
    app_config_dbsession_from_env.add_settings(enforce_https=False)

    app = app_config_dbsession_from_env.make_wsgi_app()

    with get_db_session_for_app_config(app_config_dbsession_from_env) as _db_session:
        # Register the app with the external test environment, telling
        # request.db to use this db_session and use the Transaction manager.
        testapp = _TestApp(
            app,
            extra_environ={
                "warehouse.db_session": _db_session,
                "tm.active": True,  # disable pyramid_tm
                "tm.manager": tm,  # pass in our own tm for the app to use
                "REMOTE_ADDR": REMOTE_ADDR,  # set the same address for all requests
            },
        )
        yield testapp


class _MockRedis:
    """
    Just enough Redis for our tests.
    In-memory only, no persistence.
    Does NOT implement the full Redis API.
    """

    def __init__(self, cache=None):
        self.cache = cache

        if not self.cache:  # pragma: no cover
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
        if hash_ not in self.cache:  # pragma: no cover
            self.cache[hash_] = dict()
        self.cache[hash_][key] = value

    def get(self, key):
        return self.cache.get(key)

    def pipeline(self):
        return self

    def register_script(self, script):
        return script  # pragma: no cover

    def scan_iter(self, search, count):
        del count  # unused
        return [key for key in self.cache.keys() if re.search(search, key)]

    def set(self, key, value, *_args, **_kwargs):
        self.cache[key] = value

    def setex(self, key, value, _seconds):
        self.cache[key] = value


@pytest.fixture
def mockredis():
    return _MockRedis()


@pytest.fixture
def gitlab_provenance() -> Provenance:
    """
    Provenance from
    https://test.pypi.org/integrity/pep740-sampleproject/1.0.0/pep740_sampleproject-1.0.0.tar.gz/provenance
    """
    return Provenance.model_validate_json(
        (_FIXTURES / "pep740-sampleproject-1.0.0.tar.gz.provenance").read_text()
    )


@pytest.fixture
def github_provenance() -> Provenance:
    """
    Provenance from
    https://pypi.org/integrity/sampleproject/4.0.0/sampleproject-4.0.0.tar.gz/provenance
    """
    return Provenance.model_validate_json(
        (_FIXTURES / "sampleproject-4.0.0.tar.gz.provenance").read_text()
    )
