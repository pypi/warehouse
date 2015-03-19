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
    class FakeConfig:
        @staticmethod
        @pretend.call_recorder
        def add_route(*args, **kwargs):
            pass

        @staticmethod
        @pretend.call_recorder
        def add_redirect(*args, **kwargs):
            pass

    config = FakeConfig()
    includeme(config)

    assert config.add_route.calls == [
        pretend.call(
            "accounts.profile",
            "/user/{username}/",
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call("accounts.login", "/account/login/"),
        pretend.call("accounts.logout", "/account/logout/"),
        pretend.call(
            "packaging.project",
            "/project/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}",
        ),
        pretend.call(
            "packaging.release",
            "/project/{name}/{version}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/{version}",
        ),
        pretend.call("packaging.file", "/packages/{path:.*}"),
        pretend.call("legacy.api.simple.index", "/simple/"),
        pretend.call(
            "legacy.api.simple.detail",
            "/simple/{name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{name}/",
        ),
        pretend.call("legacy.docs", "https://pythonhosted.org/{project}/"),
    ]

    assert config.add_redirect.calls == [
        pretend.call("/pypi/{name}/", "/project/{name}/"),
        pretend.call("/pypi/{name}/{version}/", "/project/{name}/{version}/"),
    ]
