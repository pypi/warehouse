# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.routes import includeme


@pytest.mark.parametrize("warehouse", [None, "pypi.io"])
def test_routes(warehouse, mocker):
    docs_route_url = mocker.sentinel.docs_route_url

    settings = {
        "docs.url": docs_route_url,
        "files.url": "https://files.example.com/packages/{path}",
    }
    if warehouse:
        settings["warehouse.domain"] = warehouse

    config = mocker.Mock(
        spec=[
            "get_settings",
            "registry",
            "add_route",
            "add_template_view",
            "add_redirect",
            "add_redirect_rule",
            "add_pypi_action_route",
            "add_pypi_action_redirect",
            "add_xmlrpc_endpoint",
        ]
    )
    config.get_settings.return_value = settings
    config.registry.settings = settings

    includeme(config)

    assert config.add_route.call_args_list == [
        mocker.call("health", "/_health/"),
        mocker.call("force-status", r"/_force-status/{status:[45]\d\d}/"),
        mocker.call("index", "/", domain=warehouse),
        mocker.call("locale", "/locale/", domain=warehouse),
        mocker.call("favicon.ico", "/favicon.ico", domain=warehouse),
        mocker.call("robots.txt", "/robots.txt", domain=warehouse),
        mocker.call(
            "funding-manifest-urls",
            "/.well-known/funding-manifest-urls",
            domain=warehouse,
        ),
        mocker.call(
            "security-txt",
            "/.well-known/security.txt",
            domain=warehouse,
        ),
        mocker.call("opensearch.xml", "/opensearch.xml", domain=warehouse),
        mocker.call("index.sitemap.xml", "/sitemap.xml", domain=warehouse),
        mocker.call("bucket.sitemap.xml", "/{bucket}.sitemap.xml", domain=warehouse),
        mocker.call(
            "includes.current-user-indicator",
            "/_includes/authed/current-user-indicator/",
            domain=warehouse,
        ),
        mocker.call(
            "includes.flash-messages",
            "/_includes/unauthed/flash-messages/",
            domain=warehouse,
        ),
        mocker.call(
            "includes.session-notifications",
            "/_includes/authed/session-notifications/",
            domain=warehouse,
        ),
        mocker.call(
            "includes.current-user-profile-callout",
            "/_includes/authed/current-user-profile-callout/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.edit-project-button",
            "/_includes/authed/edit-project-button/{project_name}",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.profile-actions",
            "/_includes/authed/profile-actions/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.profile-public-email",
            "/_includes/authed/profile-public-email/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.sidebar-sponsor-logo",
            "/_includes/unauthed/sidebar-sponsor-logo/",
            domain=warehouse,
        ),
        mocker.call(
            "includes.administer-project-include",
            "/_includes/authed/administer-project-include/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.administer-user-include",
            "/_includes/authed/administer-user-include/{user_name}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{user_name}",
            domain=warehouse,
        ),
        mocker.call(
            "includes.administer-organization-include",
            "/_includes/authed/administer-organization-include/{organization}",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization}",
            domain=warehouse,
        ),
        mocker.call("classifiers", "/classifiers/", domain=warehouse),
        mocker.call("search", "/search/", domain=warehouse),
        mocker.call("stats", "/stats/", accept="text/html", domain=warehouse),
        mocker.call(
            "stats.json", "/stats/", accept="application/json", domain=warehouse
        ),
        mocker.call(
            "security-key-giveaway", "/security-key-giveaway/", domain=warehouse
        ),
        mocker.call(
            "accounts.profile",
            "/user/{username}/",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        mocker.call("accounts.search", "/accounts/search/", domain=warehouse),
        mocker.call(
            "organizations.profile",
            "/org/{organization}/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization}",
            domain=warehouse,
        ),
        mocker.call("accounts.login", "/account/login/", domain=warehouse),
        mocker.call("accounts.two-factor", "/account/two-factor/", domain=warehouse),
        mocker.call(
            "accounts.webauthn-authenticate.options",
            "/account/webauthn-authenticate/options",
            domain=warehouse,
        ),
        mocker.call(
            "accounts.webauthn-authenticate.validate",
            "/account/webauthn-authenticate/validate",
            domain=warehouse,
        ),
        mocker.call(
            "accounts.reauthenticate", "/account/reauthenticate/", domain=warehouse
        ),
        mocker.call(
            "accounts.recovery-code", "/account/recovery-code/", domain=warehouse
        ),
        mocker.call("accounts.logout", "/account/logout/", domain=warehouse),
        mocker.call("accounts.register", "/account/register/", domain=warehouse),
        mocker.call(
            "accounts.request-password-reset",
            "/account/request-password-reset/",
            domain=warehouse,
        ),
        mocker.call(
            "accounts.reset-password", "/account/reset-password/", domain=warehouse
        ),
        mocker.call(
            "accounts.confirm-login", "/account/confirm-login/", domain=warehouse
        ),
        mocker.call(
            "accounts.verify-email", "/account/verify-email/", domain=warehouse
        ),
        mocker.call(
            "accounts.verify-organization-role",
            "/account/verify-organization-role/",
            domain=warehouse,
        ),
        mocker.call(
            "accounts.verify-project-role",
            "/account/verify-project-role/",
            domain=warehouse,
        ),
        mocker.call(
            "accounts.view-terms-of-service",
            "/account/view-terms-of-service/",
            domain=warehouse,
        ),
        mocker.call(
            "manage.unverified-account", "/manage/unverified-account/", domain=warehouse
        ),
        mocker.call("manage.account", "/manage/account/", domain=warehouse),
        mocker.call(
            "manage.account.publishing", "/manage/account/publishing/", domain=warehouse
        ),
        mocker.call(
            "manage.account.two-factor",
            "/manage/account/two-factor/",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.totp-provision",
            "/manage/account/totp-provision",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.totp-provision.image",
            "/manage/account/totp-provision/image",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.webauthn-provision",
            "/manage/account/webauthn-provision",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.webauthn-provision.options",
            "/manage/account/webauthn-provision/options",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.webauthn-provision.validate",
            "/manage/account/webauthn-provision/validate",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.webauthn-provision.delete",
            "/manage/account/webauthn-provision/delete",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.recovery-codes.generate",
            "/manage/account/recovery-codes/generate",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.recovery-codes.regenerate",
            "/manage/account/recovery-codes/regenerate",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.recovery-codes.burn",
            "/manage/account/recovery-codes/burn",
            domain=warehouse,
        ),
        mocker.call("manage.account.token", "/manage/account/token/", domain=warehouse),
        mocker.call(
            "manage.account.associations.github.connect",
            "/manage/account/associations/github/connect",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.associations.github.callback",
            "/manage/account/associations/github/callback",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.associations.gitlab.connect",
            "/manage/account/associations/gitlab/connect",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.associations.gitlab.callback",
            "/manage/account/associations/gitlab/callback",
            domain=warehouse,
        ),
        mocker.call(
            "manage.account.associations.delete",
            "/manage/account/associations/delete",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organizations.application",
            "/manage/organizations/application/{organization_application_id}/",
            factory="warehouse.organizations.models:OrganizationApplicationFactory",
            traverse="/{organization_application_id}",
            domain=warehouse,
        ),
        mocker.call("manage.organizations", "/manage/organizations/", domain=warehouse),
        mocker.call(
            "manage.organization.settings",
            "/manage/organization/{organization_name}/settings/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.activate_subscription",
            "/manage/organization/{organization_name}/subscription/activate/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.subscription",
            "/manage/organization/{organization_name}/subscription/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.projects",
            "/manage/organization/{organization_name}/projects/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.teams",
            "/manage/organization/{organization_name}/teams/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.publishing",
            "/manage/organization/{organization_name}/publishing/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.roles",
            "/manage/organization/{organization_name}/people/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.revoke_invite",
            "/manage/organization/{organization_name}/people/revoke_invite/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.resend_invite",
            "/manage/organization/{organization_name}/people/resend_invite/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.change_role",
            "/manage/organization/{organization_name}/people/change/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.delete_role",
            "/manage/organization/{organization_name}/people/delete/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.organization.history",
            "/manage/organization/{organization_name}/history/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.team.settings",
            "/manage/organization/{organization_name}/team/{team_name}/settings/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.team.projects",
            "/manage/organization/{organization_name}/team/{team_name}/projects/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.team.roles",
            "/manage/organization/{organization_name}/team/{team_name}/members/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.team.delete_role",
            "/manage/organization/{organization_name}/team/{team_name}/members/delete/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.team.history",
            "/manage/organization/{organization_name}/team/{team_name}/history/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        mocker.call("manage.projects", "/manage/projects/", domain=warehouse),
        mocker.call(
            "manage.project.settings",
            "/manage/project/{project_name}/settings/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.settings.publishing",
            "/manage/project/{project_name}/settings/publishing/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.remove_organization_project",
            "/manage/project/{project_name}/remove_organization_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.transfer_organization_project",
            "/manage/project/{project_name}/transfer_organization_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.delete_project",
            "/manage/project/{project_name}/delete_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.destroy_docs",
            "/manage/project/{project_name}/delete_project_docs/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.releases",
            "/manage/project/{project_name}/releases/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.release",
            "/manage/project/{project_name}/release/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.roles",
            "/manage/project/{project_name}/collaboration/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.revoke_invite",
            "/manage/project/{project_name}/collaboration/revoke_invite/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.change_role",
            "/manage/project/{project_name}/collaboration/change/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.delete_role",
            "/manage/project/{project_name}/collaboration/delete/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.change_team_project_role",
            "/manage/project/{project_name}/collaboration/change_team/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.delete_team_project_role",
            "/manage/project/{project_name}/collaboration/delete_team/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.documentation",
            "/manage/project/{project_name}/documentation/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.archive",
            "/manage/project/{project_name}/archive/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.unarchive",
            "/manage/project/{project_name}/unarchive/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.history",
            "/manage/project/{project_name}/history/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "manage.project.size_limit_request",
            "/manage/project/{project_name}/size-limit-request/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        mocker.call(
            "packaging.project",
            "/project/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            domain=warehouse,
        ),
        mocker.call(
            "packaging.project.submit_malware_observation",
            "/project/{name}/submit-malware-report/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            domain=warehouse,
        ),
        mocker.call(
            "packaging.release",
            "/project/{name}/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            domain=warehouse,
        ),
        mocker.call("packaging.file", "https://files.example.com/packages/{path}"),
        mocker.call("ses.hook", "/_/ses-hook/", domain=warehouse),
        mocker.call("rss.updates", "/rss/updates.xml", domain=warehouse),
        mocker.call("rss.packages", "/rss/packages.xml", domain=warehouse),
        mocker.call(
            "rss.project.releases",
            "/rss/project/{name}/releases.xml",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            domain=warehouse,
        ),
        mocker.call(
            "integrations.secrets.disclose-token",
            "/_/secrets/disclose-token",
            domain=warehouse,
        ),
        mocker.call(
            "integrations.github.disclose-token",
            "/_/github/disclose-token",
            domain=warehouse,
        ),
        mocker.call(
            "integrations.vulnerabilities.osv.report",
            "/_/vulnerabilities/osv/report",
            domain=warehouse,
        ),
        mocker.call("api.billing.webhook", "/billing/webhook/", domain=warehouse),
        mocker.call("api.simple.index", "/simple/", domain=warehouse),
        mocker.call(
            "api.simple.detail",
            "/simple/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            domain=warehouse,
        ),
        # API URLs
        mocker.call(
            "api.echo",
            "/danger-api/echo",
            auth_methods={"macaroon"},
            domain=warehouse,
        ),
        mocker.call(
            "api.projects.observations",
            "/danger-api/projects/{name}/observations",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            auth_methods={"macaroon"},
            domain=warehouse,
        ),
        # PEP 740 URLs
        mocker.call(
            "integrity.provenance",
            "/integrity/{project_name}/{release}/{filename}/provenance",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{release}/{filename}",
            domain=warehouse,
        ),
        # Mock URLs
        mocker.call(
            "mock.billing.checkout-session",
            "/mock/billing/{organization_name}/checkout/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "mock.billing.portal-session",
            "/mock/billing/{organization_name}/portal/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "mock.billing.trigger-checkout-session-completed",
            "/mock/billing/{organization_name}/checkout/completed/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        mocker.call(
            "legacy.api.json.project",
            "/pypi/{name}/json",
            factory="warehouse.legacy.api.json.latest_release_factory",
            domain=warehouse,
        ),
        mocker.call(
            "legacy.api.json.project_slash",
            "/pypi/{name}/json/",
            factory="warehouse.legacy.api.json.latest_release_factory",
            domain=warehouse,
        ),
        mocker.call(
            "legacy.api.json.release",
            "/pypi/{name}/{version}/json",
            factory="warehouse.legacy.api.json.release_factory",
            domain=warehouse,
        ),
        mocker.call(
            "legacy.api.json.release_slash",
            "/pypi/{name}/{version}/json/",
            factory="warehouse.legacy.api.json.release_factory",
            domain=warehouse,
        ),
        mocker.call("legacy.docs", docs_route_url),
    ]

    assert config.add_template_view.call_args_list == [
        mocker.call(
            "sitemap",
            "/sitemap/",
            "pages/sitemap.html",
            route_kw={"domain": warehouse},
            view_kw={"has_translations": True},
        ),
        mocker.call(
            "help",
            "/help/",
            "pages/help.html",
            route_kw={"domain": warehouse},
            view_kw={"has_translations": True},
        ),
        mocker.call(
            "security",
            "/security/",
            "pages/security.html",
            route_kw={"domain": warehouse},
            view_kw={"has_translations": True},
        ),
        mocker.call(
            "sponsors",
            "/sponsors/",
            "pages/sponsors.html",
            route_kw={"domain": warehouse},
            view_kw={"has_translations": True},
        ),
        mocker.call(
            "trademarks",
            "/trademarks/",
            "pages/trademarks.html",
            route_kw={"domain": warehouse},
            view_kw={"has_translations": True},
        ),
    ]

    assert config.add_redirect.call_args_list == [
        mocker.call("/sponsor/", "/sponsors/", domain=warehouse),
        mocker.call("/u/{username}/", "/user/{username}/", domain=warehouse),
        mocker.call("/2fa/", "/manage/account/two-factor/", domain=warehouse),
        mocker.call("/p/{name}/", "/project/{name}/", domain=warehouse),
        mocker.call(
            "/p/{name}/{version}/", "/project/{name}/{version}/", domain=warehouse
        ),
        mocker.call("/pypi/{name}/", "/project/{name}/", domain=warehouse),
        mocker.call(
            "/pypi/{name}/{version}/", "/project/{name}/{version}/", domain=warehouse
        ),
        mocker.call("/pypi/", "/", domain=warehouse),
        mocker.call(
            "/packages/{path:.*}",
            "https://files.example.com/packages/{path}",
            domain=warehouse,
        ),
    ]

    assert config.add_redirect_rule.call_args_list == [
        mocker.call(
            f"https?://({warehouse}|localhost)/policy/terms-of-use/",
            "https://policies.python.org/pypi.org/Terms-of-Use/",
        ),
        mocker.call(
            f"https?://({warehouse}|localhost)/policy/acceptable-use-policy/",
            "https://policies.python.org/pypi.org/Acceptable-Use-Policy/",
        ),
    ]

    assert config.add_pypi_action_route.call_args_list == [
        mocker.call("legacy.api.pypi.file_upload", "file_upload", domain=warehouse),
        mocker.call("legacy.api.pypi.submit", "submit", domain=warehouse),
        mocker.call(
            "legacy.api.pypi.submit_pkg_info", "submit_pkg_info", domain=warehouse
        ),
        mocker.call("legacy.api.pypi.doc_upload", "doc_upload", domain=warehouse),
        mocker.call("legacy.api.pypi.doap", "doap", domain=warehouse),
        mocker.call(
            "legacy.api.pypi.list_classifiers", "list_classifiers", domain=warehouse
        ),
        mocker.call("legacy.api.pypi.search", "search", domain=warehouse),
        mocker.call("legacy.api.pypi.browse", "browse", domain=warehouse),
        mocker.call("legacy.api.pypi.files", "files", domain=warehouse),
        mocker.call("legacy.api.pypi.display", "display", domain=warehouse),
    ]

    assert config.add_pypi_action_redirect.call_args_list == [
        mocker.call("rss", "/rss/updates.xml", domain=warehouse),
        mocker.call("packages_rss", "/rss/packages.xml", domain=warehouse),
    ]

    assert config.add_xmlrpc_endpoint.call_args_list == [
        mocker.call(
            "xmlrpc.pypi",
            pattern="/pypi",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        mocker.call(
            "xmlrpc.pypi_slash",
            pattern="/pypi/",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        mocker.call(
            "xmlrpc.RPC2",
            pattern="/RPC2",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
    ]
