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

from warehouse.routes import includeme


@pytest.mark.parametrize("warehouse", [None, "pypi.io"])
def test_routes(warehouse):
    docs_route_url = pretend.stub()

    class FakeConfig:
        def __init__(self):
            self.registry = pretend.stub(
                settings={
                    "docs.url": docs_route_url,
                    "files.url": "https://files.example.com/packages/{path}",
                }
            )
            if warehouse:
                self.registry.settings["warehouse.domain"] = warehouse

        def get_settings(self):
            return self.registry.settings

        @staticmethod
        @pretend.call_recorder
        def add_route(*args, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_template_view(*args, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_redirect(*args, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_pypi_action_route(name, action, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_pypi_action_redirect(action, target, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_xmlrpc_endpoint(endpoint, pattern, header, domain=None):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_redirect_rule(*args, **kwargs):
            pass

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call("health", "/_health/"),
        pretend.call("force-status", r"/_force-status/{status:[45]\d\d}/"),
        pretend.call("index", "/", domain=warehouse),
        pretend.call("locale", "/locale/", domain=warehouse),
        pretend.call("robots.txt", "/robots.txt", domain=warehouse),
        pretend.call("opensearch.xml", "/opensearch.xml", domain=warehouse),
        pretend.call("index.sitemap.xml", "/sitemap.xml", domain=warehouse),
        pretend.call("bucket.sitemap.xml", "/{bucket}.sitemap.xml", domain=warehouse),
        pretend.call(
            "includes.current-user-indicator",
            "/_includes/current-user-indicator/",
            domain=warehouse,
        ),
        pretend.call(
            "includes.flash-messages", "/_includes/flash-messages/", domain=warehouse
        ),
        pretend.call(
            "includes.session-notifications",
            "/_includes/session-notifications/",
            domain=warehouse,
        ),
        pretend.call(
            "includes.current-user-profile-callout",
            "/_includes/current-user-profile-callout/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.edit-project-button",
            "/_includes/edit-project-button/{project_name}",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.profile-actions",
            "/_includes/profile-actions/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.profile-public-email",
            "/_includes/profile-public-email/{username}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.sidebar-sponsor-logo",
            "/_includes/sidebar-sponsor-logo/",
            domain=warehouse,
        ),
        pretend.call(
            "includes.administer-project-include",
            "/_includes/administer-project-include/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.administer-user-include",
            "/_includes/administer-user-include/{user_name}",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{user_name}",
            domain=warehouse,
        ),
        pretend.call(
            "includes.submit_malware_report",
            "/_includes/submit-malware-report/{project_name}",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call("classifiers", "/classifiers/", domain=warehouse),
        pretend.call("search", "/search/", domain=warehouse),
        pretend.call("stats", "/stats/", accept="text/html", domain=warehouse),
        pretend.call(
            "stats.json", "/stats/", accept="application/json", domain=warehouse
        ),
        pretend.call(
            "security-key-giveaway", "/security-key-giveaway/", domain=warehouse
        ),
        pretend.call(
            "accounts.profile",
            "/user/{username}/",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        pretend.call("accounts.search", "/accounts/search/", domain=warehouse),
        pretend.call(
            "organizations.profile",
            "/org/{organization}/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization}",
            domain=warehouse,
        ),
        pretend.call("accounts.login", "/account/login/", domain=warehouse),
        pretend.call("accounts.two-factor", "/account/two-factor/", domain=warehouse),
        pretend.call(
            "accounts.webauthn-authenticate.options",
            "/account/webauthn-authenticate/options",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.webauthn-authenticate.validate",
            "/account/webauthn-authenticate/validate",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.reauthenticate", "/account/reauthenticate/", domain=warehouse
        ),
        pretend.call(
            "accounts.recovery-code", "/account/recovery-code/", domain=warehouse
        ),
        pretend.call("accounts.logout", "/account/logout/", domain=warehouse),
        pretend.call("accounts.register", "/account/register/", domain=warehouse),
        pretend.call(
            "accounts.request-password-reset",
            "/account/request-password-reset/",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.reset-password", "/account/reset-password/", domain=warehouse
        ),
        pretend.call(
            "accounts.verify-email", "/account/verify-email/", domain=warehouse
        ),
        pretend.call(
            "accounts.verify-organization-role",
            "/account/verify-organization-role/",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.verify-project-role",
            "/account/verify-project-role/",
            domain=warehouse,
        ),
        pretend.call(
            "manage.unverified-account", "/manage/unverified-account/", domain=warehouse
        ),
        pretend.call("manage.account", "/manage/account/", domain=warehouse),
        pretend.call(
            "manage.account.publishing", "/manage/account/publishing/", domain=warehouse
        ),
        pretend.call(
            "manage.account.two-factor",
            "/manage/account/two-factor/",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.totp-provision",
            "/manage/account/totp-provision",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.totp-provision.image",
            "/manage/account/totp-provision/image",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.webauthn-provision",
            "/manage/account/webauthn-provision",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.webauthn-provision.options",
            "/manage/account/webauthn-provision/options",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.webauthn-provision.validate",
            "/manage/account/webauthn-provision/validate",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.webauthn-provision.delete",
            "/manage/account/webauthn-provision/delete",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.recovery-codes.generate",
            "/manage/account/recovery-codes/generate",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.recovery-codes.regenerate",
            "/manage/account/recovery-codes/regenerate",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.recovery-codes.burn",
            "/manage/account/recovery-codes/burn",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account.token", "/manage/account/token/", domain=warehouse
        ),
        pretend.call(
            "manage.organizations", "/manage/organizations/", domain=warehouse
        ),
        pretend.call(
            "manage.organization.settings",
            "/manage/organization/{organization_name}/settings/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.activate_subscription",
            "/manage/organization/{organization_name}/subscription/activate/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.subscription",
            "/manage/organization/{organization_name}/subscription/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.projects",
            "/manage/organization/{organization_name}/projects/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.teams",
            "/manage/organization/{organization_name}/teams/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.roles",
            "/manage/organization/{organization_name}/people/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.revoke_invite",
            "/manage/organization/{organization_name}/people/revoke_invite/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.resend_invite",
            "/manage/organization/{organization_name}/people/resend_invite/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.change_role",
            "/manage/organization/{organization_name}/people/change/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.delete_role",
            "/manage/organization/{organization_name}/people/delete/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.organization.history",
            "/manage/organization/{organization_name}/history/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.team.settings",
            "/manage/organization/{organization_name}/team/{team_name}/settings/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.team.projects",
            "/manage/organization/{organization_name}/team/{team_name}/projects/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.team.roles",
            "/manage/organization/{organization_name}/team/{team_name}/members/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.team.delete_role",
            "/manage/organization/{organization_name}/team/{team_name}/members/delete/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.team.history",
            "/manage/organization/{organization_name}/team/{team_name}/history/",
            factory="warehouse.organizations.models:TeamFactory",
            traverse="/{organization_name}/{team_name}",
            domain=warehouse,
        ),
        pretend.call("manage.projects", "/manage/projects/", domain=warehouse),
        pretend.call(
            "manage.project.settings",
            "/manage/project/{project_name}/settings/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.settings.publishing",
            "/manage/project/{project_name}/settings/publishing/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.remove_organization_project",
            "/manage/project/{project_name}/remove_organization_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.transfer_organization_project",
            "/manage/project/{project_name}/transfer_organization_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.delete_project",
            "/manage/project/{project_name}/delete_project/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.destroy_docs",
            "/manage/project/{project_name}/delete_project_docs/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.releases",
            "/manage/project/{project_name}/releases/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.release",
            "/manage/project/{project_name}/release/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.roles",
            "/manage/project/{project_name}/collaboration/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.revoke_invite",
            "/manage/project/{project_name}/collaboration/revoke_invite/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.change_role",
            "/manage/project/{project_name}/collaboration/change/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.delete_role",
            "/manage/project/{project_name}/collaboration/delete/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.change_team_project_role",
            "/manage/project/{project_name}/collaboration/change_team/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.delete_team_project_role",
            "/manage/project/{project_name}/collaboration/delete_team/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.documentation",
            "/manage/project/{project_name}/documentation/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "manage.project.history",
            "/manage/project/{project_name}/history/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "packaging.project",
            "/project/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            domain=warehouse,
        ),
        pretend.call(
            "packaging.project.submit_malware_observation",
            "/project/{name}/submit-malware-report/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            domain=warehouse,
        ),
        pretend.call(
            "packaging.release",
            "/project/{name}/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            domain=warehouse,
        ),
        pretend.call("packaging.file", "https://files.example.com/packages/{path}"),
        pretend.call("ses.hook", "/_/ses-hook/", domain=warehouse),
        pretend.call("rss.updates", "/rss/updates.xml", domain=warehouse),
        pretend.call("rss.packages", "/rss/packages.xml", domain=warehouse),
        pretend.call(
            "rss.project.releases",
            "/rss/project/{name}/releases.xml",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            domain=warehouse,
        ),
        pretend.call(
            "integrations.github.disclose-token",
            "/_/github/disclose-token",
            domain=warehouse,
        ),
        pretend.call(
            "integrations.vulnerabilities.osv.report",
            "/_/vulnerabilities/osv/report",
            domain=warehouse,
        ),
        pretend.call("api.billing.webhook", "/billing/webhook/", domain=warehouse),
        pretend.call("api.simple.index", "/simple/", domain=warehouse),
        pretend.call(
            "api.simple.detail",
            "/simple/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            domain=warehouse,
        ),
        # API URLs
        pretend.call(
            "api.echo",
            "/danger-api/echo",
            domain=warehouse,
        ),
        pretend.call(
            "api.projects.observations",
            "/danger-api/projects/{name}/observations",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            domain=warehouse,
        ),
        # Mock URLs
        pretend.call(
            "mock.billing.checkout-session",
            "/mock/billing/{organization_name}/checkout/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "mock.billing.portal-session",
            "/mock/billing/{organization_name}/portal/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "mock.billing.trigger-checkout-session-completed",
            "/mock/billing/{organization_name}/checkout/completed/",
            factory="warehouse.organizations.models:OrganizationFactory",
            traverse="/{organization_name}",
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.project",
            "/pypi/{name}/json",
            factory="warehouse.legacy.api.json.latest_release_factory",
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.project_slash",
            "/pypi/{name}/json/",
            factory="warehouse.legacy.api.json.latest_release_factory",
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.release",
            "/pypi/{name}/{version}/json",
            factory="warehouse.legacy.api.json.release_factory",
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.release_slash",
            "/pypi/{name}/{version}/json/",
            factory="warehouse.legacy.api.json.release_factory",
            domain=warehouse,
        ),
        pretend.call("legacy.docs", docs_route_url),
    ]

    assert config.add_template_view.calls == [
        pretend.call(
            "sitemap",
            "/sitemap/",
            "pages/sitemap.html",
            view_kw={"has_translations": True},
        ),
        pretend.call(
            "help", "/help/", "pages/help.html", view_kw={"has_translations": True}
        ),
        pretend.call(
            "security",
            "/security/",
            "pages/security.html",
            view_kw={"has_translations": True},
        ),
        pretend.call(
            "sponsors",
            "/sponsors/",
            "pages/sponsors.html",
            view_kw={"has_translations": True},
        ),
        pretend.call(
            "trademarks",
            "/trademarks/",
            "pages/trademarks.html",
            view_kw={"has_translations": True},
        ),
    ]

    assert config.add_redirect.calls == [
        pretend.call("/sponsor/", "/sponsors/", domain=warehouse),
        pretend.call("/u/{username}/", "/user/{username}/", domain=warehouse),
        pretend.call("/2fa/", "/manage/account/two-factor/", domain=warehouse),
        pretend.call("/p/{name}/", "/project/{name}/", domain=warehouse),
        pretend.call("/pypi/{name}/", "/project/{name}/", domain=warehouse),
        pretend.call(
            "/pypi/{name}/{version}/", "/project/{name}/{version}/", domain=warehouse
        ),
        pretend.call("/pypi/", "/", domain=warehouse),
        pretend.call(
            "/packages/{path:.*}",
            "https://files.example.com/packages/{path}",
            domain=warehouse,
        ),
    ]

    assert config.add_redirect_rule.calls == [
        pretend.call(
            f"https?://({warehouse}|localhost)/policy/terms-of-use/",
            "https://policies.python.org/pypi.org/Terms-of-use/",
        ),
        pretend.call(
            f"https?://({warehouse}|localhost)/policy/acceptable-use-policy/",
            "https://policies.python.org/pypi.org/Acceptable-Use-Policy/",
        ),
    ]

    assert config.add_pypi_action_route.calls == [
        pretend.call("legacy.api.pypi.file_upload", "file_upload", domain=warehouse),
        pretend.call("legacy.api.pypi.submit", "submit", domain=warehouse),
        pretend.call(
            "legacy.api.pypi.submit_pkg_info", "submit_pkg_info", domain=warehouse
        ),
        pretend.call("legacy.api.pypi.doc_upload", "doc_upload", domain=warehouse),
        pretend.call("legacy.api.pypi.doap", "doap", domain=warehouse),
        pretend.call(
            "legacy.api.pypi.list_classifiers", "list_classifiers", domain=warehouse
        ),
        pretend.call("legacy.api.pypi.search", "search", domain=warehouse),
        pretend.call("legacy.api.pypi.browse", "browse", domain=warehouse),
        pretend.call("legacy.api.pypi.files", "files", domain=warehouse),
        pretend.call("legacy.api.pypi.display", "display", domain=warehouse),
    ]

    assert config.add_pypi_action_redirect.calls == [
        pretend.call("rss", "/rss/updates.xml", domain=warehouse),
        pretend.call("packages_rss", "/rss/packages.xml", domain=warehouse),
    ]

    assert config.add_xmlrpc_endpoint.calls == [
        pretend.call(
            "xmlrpc.pypi",
            pattern="/pypi",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        pretend.call(
            "xmlrpc.pypi_slash",
            pattern="/pypi/",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        pretend.call(
            "xmlrpc.RPC2",
            pattern="/RPC2",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
    ]
