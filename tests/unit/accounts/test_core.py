# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from celery.schedules import crontab
from pyramid.testing import DummySecurityPolicy

from warehouse import accounts
from warehouse.accounts.interfaces import (
    IDomainStatusService,
    IEmailBreachedService,
    IEmailReputationService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.services import (
    HaveIBeenPwnedEmailBreachedService,
    HaveIBeenPwnedPasswordBreachedService,
    NullDomainStatusService,
    NullEmailReputationService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.accounts.tasks import compute_user_metrics
from warehouse.accounts.utils import UserContext
from warehouse.api.maintainer._utils import ApiKeyContext
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import OIDCPublisher
from warehouse.oidc.utils import PublisherTokenContext

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory


class TestUser:
    def test_with_user_context_no_macaroon(self, pyramid_config, pyramid_request):
        user = UserFactory.build()
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=UserContext(user, None))
        )

        assert accounts._user(pyramid_request) is user

    def test_with_user_token_context_macaroon(
        self, pyramid_config, pyramid_request, mocker
    ):
        user = UserFactory.build()
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=UserContext(user, mocker.sentinel.macaroon))
        )

        assert accounts._user(pyramid_request) is user

    def test_with_api_key_context(self, pyramid_config, pyramid_request, mocker):
        user = UserFactory.build()
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=user, api_key=mocker.sentinel.api_key)
            )
        )

        assert accounts._user(pyramid_request) is user

    def test_without_user_identity(self, pyramid_config, pyramid_request, mocker):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=mocker.sentinel.nonuser)
        )

        assert accounts._user(pyramid_request) is None

    def test_without_identity(self, pyramid_request):
        assert accounts._user(pyramid_request) is None


class TestOIDCPublisherAndClaims:
    def test_with_oidc_publisher(self, pyramid_config, pyramid_request):
        publisher = GitHubPublisherFactory.create()
        assert isinstance(publisher, OIDCPublisher)
        claims = SignedClaims({"foo": "bar"})
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=PublisherTokenContext(publisher, claims))
        )

        assert accounts._oidc_publisher(pyramid_request) is publisher
        assert accounts._oidc_claims(pyramid_request) is claims

    def test_without_oidc_publisher_identity(
        self, pyramid_config, pyramid_request, mocker
    ):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=mocker.sentinel.nonpublisher)
        )

        assert accounts._oidc_publisher(pyramid_request) is None
        assert accounts._oidc_claims(pyramid_request) is None

    def test_without_identity(self, pyramid_request):
        assert accounts._oidc_publisher(pyramid_request) is None
        assert accounts._oidc_claims(pyramid_request) is None


class TestUnauthenticatedUserid:
    def test_unauthenticated_userid(self, mocker):
        assert accounts._unauthenticated_userid(mocker.sentinel.request) is None


@pytest.fixture
def config(mocker):
    config = mocker.Mock(
        spec=[
            "registry",
            "register_service_factory",
            "register_rate_limiter",
            "add_request_method",
            "set_security_policy",
            "maybe_dotted",
            "add_route_predicate",
            "add_periodic_task",
        ]
    )
    config.registry = types.SimpleNamespace(
        settings={
            "warehouse.account.user_login_ratelimit_string": "10 per 5 minutes",
            "warehouse.account.ip_login_ratelimit_string": "10 per 5 minutes",
            "warehouse.account.global_login_ratelimit_string": "1000 per 5 minutes",
            "warehouse.account.2fa_user_ratelimit_string": "5 per 5 minutes, 20 per hour, 50 per day",  # noqa: E501
            "warehouse.account.2fa_ip_ratelimit_string": "10 per 5 minutes, 50 per hour",  # noqa: E501
            "warehouse.account.email_add_ratelimit_string": "2 per day",
            "warehouse.account.email_change_ratelimit_string": "5 per 5 minutes, 20 per hour",  # noqa: E501
            "warehouse.account.email_reputation_ratelimit_string": "100 per hour",
            "warehouse.account.verify_email_ratelimit_string": "3 per 6 hours",
            "warehouse.account.password_reset_ratelimit_string": "5 per day",
            "warehouse.account.password_reset_ip_ratelimit_string": "10 per hour",
            "warehouse.account.accounts_search_ratelimit_string": "100 per hour",
            "warehouse.account.register_ratelimit_string": "10 per 5 minutes, 30 per hour",  # noqa: E501
            "github.oauth.backend": accounts.NullGitHubOAuthClient,
        }
    )
    config.maybe_dotted.side_effect = lambda path: path
    return config


def test_includeme(config, mocker):
    multi_policy_cls = mocker.patch.object(
        accounts, "MultiSecurityPolicy", autospec=True
    )
    session_policy_cls = mocker.patch.object(
        accounts, "SessionSecurityPolicy", autospec=True
    )
    basic_policy_cls = mocker.patch.object(
        accounts, "BasicAuthSecurityPolicy", autospec=True
    )
    macaroon_policy_cls = mocker.patch.object(
        accounts, "MacaroonSecurityPolicy", autospec=True
    )
    api_key_policy_cls = mocker.patch.object(
        accounts, "ApiKeySecurityPolicy", autospec=True
    )

    accounts.includeme(config)

    assert config.register_service_factory.call_args_list == [
        mocker.call(database_login_factory, IUserService),
        mocker.call(
            TokenServiceFactory(name="password"), ITokenService, name="password"
        ),
        mocker.call(TokenServiceFactory(name="email"), ITokenService, name="email"),
        mocker.call(
            TokenServiceFactory(name="two_factor"), ITokenService, name="two_factor"
        ),
        mocker.call(
            TokenServiceFactory(name="confirm_login"),
            ITokenService,
            name="confirm_login",
        ),
        mocker.call(
            TokenServiceFactory(name="remember_device"),
            ITokenService,
            name="remember_device",
        ),
        mocker.call(
            HaveIBeenPwnedPasswordBreachedService.create_service,
            IPasswordBreachedService,
        ),
        mocker.call(
            HaveIBeenPwnedEmailBreachedService.create_service,
            IEmailBreachedService,
        ),
        mocker.call(NullDomainStatusService.create_service, IDomainStatusService),
        mocker.call(
            NullEmailReputationService.create_service,
            IEmailReputationService,
        ),
        mocker.call(
            accounts.NullGitHubOAuthClient.create_service,
            accounts.IOAuthProviderService,
            name="github",
        ),
    ]
    assert config.register_rate_limiter.call_args_list == [
        mocker.call("10 per 5 minutes", "user.login"),
        mocker.call("10 per 5 minutes", "ip.login"),
        mocker.call("1000 per 5 minutes", "global.login"),
        mocker.call("5 per 5 minutes, 20 per hour, 50 per day", "2fa.user"),
        mocker.call("10 per 5 minutes, 50 per hour", "2fa.ip"),
        mocker.call("2 per day", "email.add"),
        mocker.call("5 per 5 minutes, 20 per hour", "email.change"),
        mocker.call("100 per hour", "email.reputation"),
        mocker.call("5 per day", "password.reset"),
        mocker.call("10 per hour", "password.reset.ip"),
        mocker.call("3 per 6 hours", "email.verify"),
        mocker.call("100 per hour", "accounts.search"),
        mocker.call("10 per 5 minutes, 30 per hour", "accounts.register"),
    ]
    assert config.add_request_method.call_args_list == [
        mocker.call(accounts._user, name="user", reify=True),
        mocker.call(accounts._oidc_publisher, name="oidc_publisher", reify=True),
        mocker.call(accounts._oidc_claims, name="oidc_claims", reify=True),
        mocker.call(accounts._unauthenticated_userid, name="_unauthenticated_userid"),
    ]
    config.set_security_policy.assert_called_once_with(multi_policy_cls.return_value)
    multi_policy_cls.assert_called_once_with(
        [
            session_policy_cls.return_value,
            basic_policy_cls.return_value,
            macaroon_policy_cls.return_value,
            api_key_policy_cls.return_value,
        ]
    )
    assert (
        mocker.call(crontab(minute="*/20"), compute_user_metrics)
        in config.add_periodic_task.call_args_list
    )


def test_includeme_with_gitlab_oauth(config, mocker):
    """Verify GitLab OAuth service is registered only when configured."""
    gitlab_registration = mocker.call(
        accounts.NullGitLabOAuthClient.create_service,
        accounts.IOAuthProviderService,
        name="gitlab",
    )

    accounts.includeme(config)
    assert gitlab_registration not in config.register_service_factory.call_args_list

    config.register_service_factory.reset_mock()
    config.registry.settings["gitlab.oauth.backend"] = accounts.NullGitLabOAuthClient
    accounts.includeme(config)
    assert gitlab_registration in config.register_service_factory.call_args_list
