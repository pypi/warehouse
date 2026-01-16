# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab

from warehouse.accounts.interfaces import (
    IDomainStatusService,
    IEmailBreachedService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.oauth import (
    GitHubAppClient,
    IOAuthProviderService,
    NullOAuthClient,
)
from warehouse.accounts.security_policy import (
    BasicAuthSecurityPolicy,
    SessionSecurityPolicy,
)
from warehouse.accounts.services import (
    HaveIBeenPwnedEmailBreachedService,
    HaveIBeenPwnedPasswordBreachedService,
    NullDomainStatusService,
    NullEmailBreachedService,
    NullPasswordBreachedService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.accounts.tasks import (
    batch_update_email_domain_status,
    compute_user_metrics,
    notify_users_of_tos_update,
    unverify_emails_with_expired_domains,
)
from warehouse.accounts.utils import UserContext
from warehouse.admin.flags import AdminFlagValue
from warehouse.macaroons.security_policy import MacaroonSecurityPolicy
from warehouse.oidc.utils import PublisherTokenContext
from warehouse.organizations.services import IOrganizationService
from warehouse.rate_limiting import IRateLimiter, RateLimit
from warehouse.utils.security_policy import MultiSecurityPolicy

__all__ = [
    "NullPasswordBreachedService",
    "HaveIBeenPwnedPasswordBreachedService",
    "NullEmailBreachedService",
    "HaveIBeenPwnedEmailBreachedService",
    "GitHubAppClient",
    "NullOAuthClient",
]


REDIRECT_FIELD_NAME = "next"


def _user(request):
    if request.identity is None:
        return None

    if isinstance(request.identity, UserContext):
        return request.identity.user
    else:
        return None


def _oidc_publisher(request):
    return (
        request.identity.publisher
        if isinstance(request.identity, PublisherTokenContext)
        else None
    )


def _oidc_claims(request):
    return (
        request.identity.claims
        if isinstance(request.identity, PublisherTokenContext)
        else None
    )


def _organization_access(request):
    if (user := _user(request)) is None:
        return False

    organization_service = request.find_service(IOrganizationService, context=None)
    organizations = organization_service.get_organizations_by_user(user.id)
    return (
        not request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS)
        or len(organizations) > 0
    )


def _unauthenticated_userid(request):
    return None


def includeme(config):
    # Register our login service
    config.register_service_factory(database_login_factory, IUserService)

    # Register our token services
    config.register_service_factory(
        TokenServiceFactory(name="password"), ITokenService, name="password"
    )
    config.register_service_factory(
        TokenServiceFactory(name="email"), ITokenService, name="email"
    )
    config.register_service_factory(
        TokenServiceFactory(name="two_factor"), ITokenService, name="two_factor"
    )
    config.register_service_factory(
        TokenServiceFactory(name="confirm_login"), ITokenService, name="confirm_login"
    )
    config.register_service_factory(
        TokenServiceFactory(name="remember_device"),
        ITokenService,
        name="remember_device",
    )

    # Register our password breach detection service.
    breached_pw_class = config.maybe_dotted(
        config.registry.settings.get(
            "breached_passwords.backend", HaveIBeenPwnedPasswordBreachedService
        )
    )
    config.register_service_factory(
        breached_pw_class.create_service, IPasswordBreachedService
    )
    # Register our email breach detection service.
    breached_email_class = config.maybe_dotted(
        config.registry.settings.get(
            "breached_emails.backend", HaveIBeenPwnedEmailBreachedService
        )
    )
    config.register_service_factory(
        breached_email_class.create_service, IEmailBreachedService
    )

    # Register our domain status service.
    domain_status_class = config.maybe_dotted(
        config.registry.settings.get("domain_status.backend", NullDomainStatusService)
    )
    config.register_service_factory(
        domain_status_class.create_service, IDomainStatusService
    )

    # Register our GitHub App service for account associations.
    # Setting must be explicitly configured - use NullOAuthClient for development
    # or GitHubAppClient for production with real GitHub App integration.
    github_app_class = config.maybe_dotted(
        config.registry.settings["github.oauth.backend"]
    )
    config.register_service_factory(
        github_app_class.create_service, IOAuthProviderService, name="github"
    )

    # Register our security policies.
    config.set_security_policy(
        MultiSecurityPolicy(
            [
                SessionSecurityPolicy(),
                BasicAuthSecurityPolicy(),
                MacaroonSecurityPolicy(),
            ],
        )
    )

    # Add a request method which will allow people to access the specific current
    # request identity by type, if they know it.
    config.add_request_method(_user, name="user", reify=True)
    config.add_request_method(_oidc_publisher, name="oidc_publisher", reify=True)
    config.add_request_method(_oidc_claims, name="oidc_claims", reify=True)
    config.add_request_method(
        _organization_access, name="organization_access", reify=True
    )

    config.add_request_method(_unauthenticated_userid, name="_unauthenticated_userid")

    # Register the rate limits that we're going to be using for our login
    # attempts and account creation
    user_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.user_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(user_login_ratelimit_string, identifiers=["user.login"]),
        IRateLimiter,
        name="user.login",
    )
    ip_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.ip_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(ip_login_ratelimit_string, identifiers=["ip.login"]),
        IRateLimiter,
        name="ip.login",
    )
    global_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.global_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(global_login_ratelimit_string, identifiers=["global.login"]),
        IRateLimiter,
        name="global.login",
    )
    # Register separate rate limiters for 2FA attempts
    twofa_user_ratelimit_string = config.registry.settings.get(
        "warehouse.account.2fa_user_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(twofa_user_ratelimit_string, identifiers=["2fa.user"]),
        IRateLimiter,
        name="2fa.user",
    )
    twofa_ip_ratelimit_string = config.registry.settings.get(
        "warehouse.account.2fa_ip_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(twofa_ip_ratelimit_string, identifiers=["2fa.ip"]),
        IRateLimiter,
        name="2fa.ip",
    )
    email_add_ratelimit_string = config.registry.settings.get(
        "warehouse.account.email_add_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(email_add_ratelimit_string, identifiers=["email.add"]),
        IRateLimiter,
        name="email.add",
    )
    password_reset_ratelimit_string = config.registry.settings.get(
        "warehouse.account.password_reset_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(password_reset_ratelimit_string, identifiers=["password.reset"]),
        IRateLimiter,
        name="password.reset",
    )
    verify_email_ratelimit_string = config.registry.settings.get(
        "warehouse.account.verify_email_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(verify_email_ratelimit_string, identifiers=["email.verify"]),
        IRateLimiter,
        name="email.verify",
    )
    accounts_search_ratelimit_string = config.registry.settings.get(
        "warehouse.account.accounts_search_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(accounts_search_ratelimit_string, identifiers=["accounts.search"]),
        IRateLimiter,
        name="accounts.search",
    )

    # Add a periodic task to generate Account metrics
    config.add_periodic_task(crontab(minute="*/20"), compute_user_metrics)
    config.add_periodic_task(crontab(minute="*"), notify_users_of_tos_update)
    config.add_periodic_task(
        crontab(minute=0, hour=4), batch_update_email_domain_status
    )
    config.add_periodic_task(
        crontab(minute=15, hour=4), unverify_emails_with_expired_domains
    )
