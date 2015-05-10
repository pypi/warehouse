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


def includeme(config):
    config.add_route("index", "/")

    # Accounts
    config.add_route(
        "accounts.profile",
        "/user/{username}/",
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route("accounts.login", "/account/login/")
    config.add_route("accounts.logout", "/account/logout/")
    config.add_route("accounts.register", "/account/register/")

    # Packaging
    config.add_route(
        "packaging.project",
        "/project/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
    )
    config.add_route(
        "packaging.release",
        "/project/{name}/{version}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
    )
    config.add_route("packaging.file", "/packages/{path:.*}")

    # Legacy URLs
    config.add_route("legacy.api.simple.index", "/simple/")
    config.add_route(
        "legacy.api.simple.detail",
        "/simple/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/",
    )
    config.add_route(
        "legacy.api.json.project",
        "/pypi/{name}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
    )
    config.add_route(
        "legacy.api.json.release",
        "/pypi/{name}/{version}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
    )

    # Legacy Documentation
    config.add_route("legacy.docs", config.registry.settings["docs.url"])

    # Legacy Redirects
    config.add_redirect("/pypi/{name}/", "/project/{name}/")
    config.add_redirect(
        "/pypi/{name}/{version}/",
        "/project/{name}/{version}/",
    )
