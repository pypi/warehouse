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

from warehouse import db


def includeme(config):
    # Accounts
    config.add_route(
        "accounts.profile",
        "/user/{username}/",
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route("accounts.login", "/account/login/")
    config.add_route("accounts.logout", "/account/logout/")

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
    config.add_route(
        "packaging.file",
        "/packages/{path:.*}",
        custom_predicates=[db.read_only],
    )

    # Legacy URLs
    config.add_route(
        "legacy.api.simple.index",
        "/simple/",
        custom_predicates=[db.read_only],
    )
    config.add_route(
        "legacy.api.simple.detail",
        "/simple/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/",
        custom_predicates=[db.read_only],
    )

    # Legacy Redirects
    config.add_redirect("/pypi/{name}/", "/project/{name}/")
    config.add_redirect(
        "/pypi/{name}/{version}/",
        "/project/{name}/{version}/",
    )
