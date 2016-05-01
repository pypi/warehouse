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


@pytest.mark.parametrize(
    ("warehouse", "forklift"),
    [
        (None, None),
        ("pypi.io", None),
        (None, "upload.pypi.io"),
        ("pypi.io", "upload.pypi.io"),
    ]
)
def test_routes(warehouse, forklift):
    docs_route_url = pretend.stub()

    class FakeConfig:

        def __init__(self):
            self.registry = pretend.stub(settings={"docs.url": docs_route_url})

        @staticmethod
        def get_settings():
            settings = {}
            if warehouse:
                settings["warehouse.domain"] = warehouse
            if forklift:
                settings["forklift.domain"] = forklift
            return settings

        @staticmethod
        @pretend.call_recorder
        def add_route(*args, **kwargs):
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

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call("health", "/_health/"),
        pretend.call('index', '/', domain=warehouse),
        pretend.call("robots.txt", "/robots.txt", domain=warehouse),
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
            "/packages/{path:[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/[^/]+}",
            domain=warehouse,
        ),
        pretend.call("rss.updates", "/rss/updates.xml", domain=warehouse),
        pretend.call("rss.packages", "/rss/packages.xml", domain=warehouse),
        pretend.call(
            "legacy.file.redirect",
            "/packages/{path:[^/]+/[^/]/[^/]+/[^/]+}",
            domain=warehouse,
        ),
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

    assert config.add_redirect.calls == [
        pretend.call("/pypi/{name}/", "/project/{name}/", domain=warehouse),
        pretend.call(
            "/pypi/{name}/{version}/",
            "/project/{name}/{version}/",
            domain=warehouse,
        ),
    ]

    assert config.add_pypi_action_route.calls == [
        pretend.call(
            "legacy.api.pypi.file_upload",
            "file_upload",
            domain=forklift,
        ),
        pretend.call("legacy.api.pypi.submit", "submit", domain=forklift),
        pretend.call(
            "legacy.api.pypi.submit_pkg_info",
            "submit_pkg_info",
            domain=forklift,
        ),
        pretend.call(
            "legacy.api.pypi.doc_upload",
            "doc_upload",
            domain=forklift,
        ),
        pretend.call("legacy.api.pypi.doap", "doap", domain=warehouse),
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
    ]
