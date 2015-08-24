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

from warehouse.db import ReadOnly
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
        def add_xmlrpc_endpoint(endpoint, pattern, header, factory):
            pass

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call('index', '/', factory=ReadOnly()),
        pretend.call(
            "accounts.profile",
            "/user/{username}/",
            factory=ReadOnly("warehouse.accounts.models:UserFactory"),
            traverse="/{username}",
        ),
        pretend.call("accounts.login", "/account/login/"),
        pretend.call("accounts.logout", "/account/logout/"),
        pretend.call(
            "packaging.project",
            "/project/{name}/",
            factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
            traverse="/{name}",
        ),
        pretend.call(
            "packaging.release",
            "/project/{name}/{version}/",
            factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
            traverse="/{name}/{version}",
        ),
        pretend.call(
            "packaging.file",
            "/packages/{path:.*}",
            factory=ReadOnly(),
        ),
        pretend.call(
            "legacy.api.simple.index",
            "/simple/",
            factory=ReadOnly(),
        ),
        pretend.call(
            "legacy.api.simple.detail",
            "/simple/{name}/",
            factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
            traverse="/{name}/",
        ),
        pretend.call(
            "legacy.api.json.project",
            "/pypi/{name}/json",
            factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
            traverse="/{name}",
        ),
        pretend.call(
            "legacy.api.json.release",
            "/pypi/{name}/{version}/json",
            factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
            traverse="/{name}/{version}",
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

    assert config.add_xmlrpc_endpoint.calls == [
        pretend.call(
            "pypi",
            pattern="/pypi",
            header="Content-Type:text/xml",
            factory=ReadOnly(),
        ),
    ]
