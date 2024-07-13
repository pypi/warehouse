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

import pretend
import pytest

from celery.schedules import crontab

from warehouse import accounts
from warehouse.accounts.interfaces import (
    IEmailBreachedService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.services import (
    HaveIBeenPwnedEmailBreachedService,
    HaveIBeenPwnedPasswordBreachedService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.accounts.tasks import compute_user_metrics
from warehouse.accounts.utils import UserContext
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import OIDCPublisher
from warehouse.oidc.utils import PublisherTokenContext
from warehouse.rate_limiting import IRateLimiter, RateLimit

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory


class TestUser:
    def test_with_user_context_no_macaroon(self, db_request):
        user = UserFactory.create()
        user_ctx = UserContext(user, None)
        request = pretend.stub(identity=user_ctx)

        assert accounts._user(request) is user

    def test_with_user_token_context_macaroon(self, db_request):
        user = UserFactory.create()
        user_ctx = UserContext(user, pretend.stub())
        request = pretend.stub(identity=user_ctx)

        assert accounts._user(request) is user

    def test_without_user_identity(self):
        nonuser = pretend.stub()
        request = pretend.stub(identity=nonuser)

        assert accounts._user(request) is None

    def test_without_identity(self):
        request = pretend.stub(identity=None)
        assert accounts._user(request) is None


class TestOIDCPublisherAndClaims:
    def test_with_oidc_publisher(self, db_request):
        publisher = GitHubPublisherFactory.create()
        assert isinstance(publisher, OIDCPublisher)
        claims = SignedClaims({"foo": "bar"})

        request = pretend.stub(identity=PublisherTokenContext(publisher, claims))

        assert accounts._oidc_publisher(request) is publisher
        assert accounts._oidc_claims(request) is claims

    def test_without_oidc_publisher_identity(self):
        nonpublisher = pretend.stub()
        request = pretend.stub(identity=nonpublisher)

        assert accounts._oidc_publisher(request) is None
        assert accounts._oidc_claims(request) is None

    def test_without_identity(self):
        request = pretend.stub(identity=None)
        assert accounts._oidc_publisher(request) is None
        assert accounts._oidc_claims(request) is None


class TestOrganizationAccess:
    @pytest.mark.parametrize(
        ["identity", "flag", "orgs", "expected"],
        [
            (False, True, [], False),  # Unauth'd always have no access
            (False, False, [], False),  # Unauth'd always have no access
            (True, False, [], True),  # Flag allows all authenticated users
            (True, True, [], False),  # Flag blocks all authenticated users without orgs
            (
                True,
                True,
                [pretend.stub()],
                True,
            ),  # Flag allows users with organizations
        ],
    )
    def test_organization_access(self, db_session, identity, flag, orgs, expected):
        user = None if not identity else UserFactory()
        request = pretend.stub(
            identity=UserContext(user, None),
            find_service=lambda interface, context=None: pretend.stub(
                get_organizations_by_user=lambda x: orgs
            ),
            flags=pretend.stub(enabled=lambda flag_name: flag),
        )
        assert expected == accounts._organization_access(request)


class TestUnauthenticatedUserid:
    def test_unauthenticated_userid(self):
        request = pretend.stub()
        assert accounts._unauthenticated_userid(request) is None


def test_includeme(monkeypatch):
    multi_policy_obj = pretend.stub()
    multi_policy_cls = pretend.call_recorder(lambda ps: multi_policy_obj)
    monkeypatch.setattr(accounts, "MultiSecurityPolicy", multi_policy_cls)

    session_policy_obj = pretend.stub()
    session_policy_cls = pretend.call_recorder(lambda: session_policy_obj)
    monkeypatch.setattr(accounts, "SessionSecurityPolicy", session_policy_cls)

    basic_policy_obj = pretend.stub()
    basic_policy_cls = pretend.call_recorder(lambda: basic_policy_obj)
    monkeypatch.setattr(accounts, "BasicAuthSecurityPolicy", basic_policy_cls)

    macaroon_policy_obj = pretend.stub()
    macaroon_policy_cls = pretend.call_recorder(lambda: macaroon_policy_obj)
    monkeypatch.setattr(accounts, "MacaroonSecurityPolicy", macaroon_policy_cls)

    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "warehouse.account.user_login_ratelimit_string": "10 per 5 minutes",
                "warehouse.account.ip_login_ratelimit_string": "10 per 5 minutes",
                "warehouse.account.global_login_ratelimit_string": "1000 per 5 minutes",
                "warehouse.account.email_add_ratelimit_string": "2 per day",
                "warehouse.account.verify_email_ratelimit_string": "3 per 6 hours",
                "warehouse.account.password_reset_ratelimit_string": "5 per day",
                "warehouse.account.accounts_search_ratelimit_string": "100 per hour",
            }
        ),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        add_request_method=pretend.call_recorder(lambda f, name, reify=False: None),
        set_security_policy=pretend.call_recorder(lambda p: None),
        maybe_dotted=pretend.call_recorder(lambda path: path),
        add_route_predicate=pretend.call_recorder(lambda name, cls: None),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    accounts.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(database_login_factory, IUserService),
        pretend.call(
            TokenServiceFactory(name="password"), ITokenService, name="password"
        ),
        pretend.call(TokenServiceFactory(name="email"), ITokenService, name="email"),
        pretend.call(
            TokenServiceFactory(name="two_factor"), ITokenService, name="two_factor"
        ),
        pretend.call(
            TokenServiceFactory(name="remember_device"),
            ITokenService,
            name="remember_device",
        ),
        pretend.call(
            HaveIBeenPwnedPasswordBreachedService.create_service,
            IPasswordBreachedService,
        ),
        pretend.call(
            HaveIBeenPwnedEmailBreachedService.create_service,
            IEmailBreachedService,
        ),
        pretend.call(RateLimit("10 per 5 minutes"), IRateLimiter, name="user.login"),
        pretend.call(RateLimit("10 per 5 minutes"), IRateLimiter, name="ip.login"),
        pretend.call(
            RateLimit("1000 per 5 minutes"), IRateLimiter, name="global.login"
        ),
        pretend.call(RateLimit("2 per day"), IRateLimiter, name="email.add"),
        pretend.call(RateLimit("5 per day"), IRateLimiter, name="password.reset"),
        pretend.call(RateLimit("3 per 6 hours"), IRateLimiter, name="email.verify"),
        pretend.call(RateLimit("100 per hour"), IRateLimiter, name="accounts.search"),
    ]
    assert config.add_request_method.calls == [
        pretend.call(accounts._user, name="user", reify=True),
        pretend.call(accounts._oidc_publisher, name="oidc_publisher", reify=True),
        pretend.call(accounts._oidc_claims, name="oidc_claims", reify=True),
        pretend.call(
            accounts._organization_access, name="organization_access", reify=True
        ),
        pretend.call(accounts._unauthenticated_userid, name="_unauthenticated_userid"),
    ]
    assert config.set_security_policy.calls == [pretend.call(multi_policy_obj)]
    assert multi_policy_cls.calls == [
        pretend.call(
            [
                session_policy_obj,
                basic_policy_obj,
                macaroon_policy_obj,
            ]
        )
    ]
    assert (
        pretend.call(crontab(minute="*/20"), compute_user_metrics)
        in config.add_periodic_task.calls
    )
