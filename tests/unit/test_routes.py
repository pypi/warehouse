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

from warehouse.routes import includeme


def test_routes():
    docs_route_url = pretend.stub()

    class FakeConfig:

        def __init__(self):
            self.registry = pretend.stub(settings={"docs.url": docs_route_url})

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
        def add_xmlrpc_endpoint(endpoint, pattern, header, read_only=False):
            pass

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call('index', '/', read_only=True),
        pretend.call("robots.txt", "/robots.txt", read_only=True),
        pretend.call("index.sitemap.xml", "/sitemap.xml", read_only=True),
        pretend.call(
            "bucket.sitemap.xml",
            "/{bucket}.sitemap.xml",
            read_only=True,
        ),
        pretend.call(
            "includes.current-user-indicator",
            "/_includes/current-user-indicator/",
            read_only=True,
        ),
        pretend.call("search", "/search/", read_only=True),
        pretend.call(
            "accounts.profile",
            "/user/{username}/",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
            read_only=True,
        ),
        pretend.call("accounts.login", "/account/login/"),
        pretend.call("accounts.logout", "/account/logout/"),
        pretend.call(
            "packaging.project",
            "/project/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            read_only=True,
        ),
        pretend.call(
            "packaging.release",
            "/project/{name}/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            read_only=True,
        ),
        pretend.call("packaging.file", "/packages/{path:.*}", read_only=True),
        pretend.call("rss.updates", "/rss/updates.xml", read_only=True),
        pretend.call("rss.packages", "/rss/packages.xml", read_only=True),
        pretend.call("legacy.api.simple.index", "/simple/", read_only=True),
        pretend.call(
            "legacy.api.simple.detail",
            "/simple/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
            read_only=True,
        ),
        pretend.call(
            "legacy.api.json.project",
            "/pypi/{name}/json",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
            read_only=True,
        ),
        pretend.call(
            "legacy.api.json.release",
            "/pypi/{name}/{version}/json",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
            read_only=True,
        ),
        pretend.call("legacy.docs", docs_route_url),
    ]

    assert config.add_redirect.calls == [
        pretend.call("/pypi/{name}/", "/project/{name}/"),
        pretend.call("/pypi/{name}/{version}/", "/project/{name}/{version}/"),
    ]

    assert config.add_pypi_action_route.calls == [
        pretend.call("legacy.api.pypi.file_upload", "file_upload"),
        pretend.call("legacy.api.pypi.submit", "submit"),
        pretend.call("legacy.api.pypi.submit_pkg_info", "submit_pkg_info"),
        pretend.call("legacy.api.pypi.doc_upload", "doc_upload"),
        pretend.call("legacy.api.pypi.doap", "doap"),
    ]

    assert config.add_pypi_action_redirect.calls == [
        pretend.call("rss", "/rss/updates.xml"),
        pretend.call("packages_rss", "/rss/packages.xml"),
    ]

    assert config.add_xmlrpc_endpoint.calls == [
        pretend.call(
            "pypi",
            pattern="/pypi",
            header="Content-Type:text/xml",
            read_only=True,
        ),
    ]
