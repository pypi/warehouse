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
            self.registry = pretend.stub(settings={
                "docs.url": docs_route_url,
                "files.url": "https://files.example.com/packages/{path}",
            })
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
        def add_policy(name, filename):
            pass

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call("health", "/_health/"),
        pretend.call("force-status", "/_force-status/{status:[45]\d\d}/"),
        pretend.call('index', '/', domain=warehouse),
        pretend.call("robots.txt", "/robots.txt", domain=warehouse),
        pretend.call("opensearch.xml", "/opensearch.xml", domain=warehouse),
        pretend.call("index.sitemap.xml", "/sitemap.xml", domain=warehouse),
        pretend.call(
            "bucket.sitemap.xml",
            "/{bucket}.sitemap.xml",
            domain=warehouse,
        ),
        pretend.call(
            "includes.current-user-indicator",
            "/_includes/current-user-indicator/",
            domain=warehouse,
        ),
        pretend.call(
            "includes.flash-messages",
            "/_includes/flash-messages/",
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
        pretend.call("classifiers", "/classifiers/", domain=warehouse),
        pretend.call("search", "/search/", domain=warehouse),
        pretend.call(
            "accounts.profile",
            "/user/{username}/",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            domain=warehouse,
        ),
        pretend.call("accounts.login", "/account/login/", domain=warehouse),
        pretend.call("accounts.logout", "/account/logout/", domain=warehouse),
        pretend.call(
            "accounts.register",
            "/account/register/",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.request-password-reset",
            "/account/request-password-reset/",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.reset-password",
            "/account/reset-password/",
            domain=warehouse,
        ),
        pretend.call(
            "accounts.verify-email",
            "/account/verify-email/",
            domain=warehouse,
        ),
        pretend.call(
            "manage.account",
            "/manage/account/",
            domain=warehouse
        ),
        pretend.call(
            "manage.projects",
            "/manage/projects/",
            domain=warehouse
        ),
        pretend.call(
            "manage.project.settings",
            "/manage/project/{project_name}/settings/",
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
            "packaging.release",
            "/project/{name}/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "packaging.file",
            "https://files.example.com/packages/{path}",
        ),
        pretend.call("ses.hook", "/_/ses-hook/", domain=warehouse),
        pretend.call("rss.updates", "/rss/updates.xml", domain=warehouse),
        pretend.call("rss.packages", "/rss/packages.xml", domain=warehouse),
        pretend.call("legacy.api.simple.index", "/simple/", domain=warehouse),
        pretend.call(
            "legacy.api.simple.detail",
            "/simple/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            read_only=True,
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.project",
            "/pypi/{name}/json",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            read_only=True,
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.json.release",
            "/pypi/{name}/{version}/json",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            read_only=True,
            domain=warehouse,
        ),
        pretend.call("legacy.docs", docs_route_url),
    ]

    assert config.add_template_view.calls == [
        pretend.call("help", "/help/", "pages/help.html"),
        pretend.call("security", "/security/", "pages/security.html"),
        pretend.call(
            "sponsors",
            "/sponsors/",
            "warehouse:templates/pages/sponsors.html",
        ),
    ]

    assert config.add_redirect.calls == [
        pretend.call("/p/{name}/", "/project/{name}/", domain=warehouse),
        pretend.call("/pypi/{name}/", "/project/{name}/", domain=warehouse),
        pretend.call(
            "/pypi/{name}/{version}/",
            "/project/{name}/{version}/",
            domain=warehouse,
        ),
        pretend.call(
            "/packages/{path:.*}",
            "https://files.example.com/packages/{path}",
            domain=warehouse,
        ),
    ]

    assert config.add_pypi_action_route.calls == [
        pretend.call(
            "legacy.api.pypi.file_upload",
            "file_upload",
            domain=warehouse,
        ),
        pretend.call("legacy.api.pypi.submit", "submit", domain=warehouse),
        pretend.call(
            "legacy.api.pypi.submit_pkg_info",
            "submit_pkg_info",
            domain=warehouse,
        ),
        pretend.call(
            "legacy.api.pypi.doc_upload",
            "doc_upload",
            domain=warehouse,
        ),
        pretend.call("legacy.api.pypi.doap", "doap", domain=warehouse),
        pretend.call(
            "legacy.api.pypi.list_classifiers",
            "list_classifiers",
            domain=warehouse,
        ),
        pretend.call(
            'legacy.api.pypi.search',
            'search',
            domain=warehouse,
        ),
        pretend.call(
            'legacy.api.pypi.browse',
            'browse',
            domain=warehouse,
        ),
        pretend.call(
            'legacy.api.pypi.files',
            'files',
            domain=warehouse,
        ),
        pretend.call(
            'legacy.api.pypi.display',
            'display',
            domain=warehouse,
        ),
    ]

    assert config.add_pypi_action_redirect.calls == [
        pretend.call("rss", "/rss/updates.xml", domain=warehouse),
        pretend.call("packages_rss", "/rss/packages.xml", domain=warehouse),
    ]

    assert config.add_xmlrpc_endpoint.calls == [
        pretend.call(
            "pypi",
            pattern="/pypi",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        pretend.call(
            "pypi_slash",
            pattern="/pypi/",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
        pretend.call(
            "RPC2",
            pattern="/RPC2",
            header="Content-Type:text/xml",
            domain=warehouse,
        ),
    ]

    assert config.add_policy.calls == [
        pretend.call("terms-of-use", "terms.md"),
    ]
