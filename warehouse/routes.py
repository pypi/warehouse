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

from warehouse.db import ReadOnly


def includeme(config):
    config.add_route("index", "/", factory=ReadOnly())

    # Accounts
    config.add_route(
        "accounts.profile",
        "/user/{username}/",
        factory=ReadOnly("warehouse.accounts.models:UserFactory"),
        traverse="/{username}",
    )
    config.add_route("accounts.login", "/account/login/")
    config.add_route("accounts.logout", "/account/logout/")

    # Packaging
    config.add_route(
        "packaging.project",
        "/project/{name}/",
        factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
        traverse="/{name}",
    )
    config.add_route(
        "packaging.release",
        "/project/{name}/{version}/",
        factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
        traverse="/{name}/{version}",
    )
    config.add_route(
        "packaging.file",
        "/packages/{path:.*}",
        factory=ReadOnly(),
    )

    # Legacy URLs
    config.add_route("legacy.api.simple.index", "/simple/", factory=ReadOnly())
    config.add_route(
        "legacy.api.simple.detail",
        "/simple/{name}/",
        factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
        traverse="/{name}/",
    )
    config.add_route(
        "legacy.api.json.project",
        "/pypi/{name}/json",
        factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
        traverse="/{name}",
    )
    config.add_route(
        "legacy.api.json.release",
        "/pypi/{name}/{version}/json",
        factory=ReadOnly("warehouse.packaging.models:ProjectFactory"),
        traverse="/{name}/{version}",
    )

    # Legacy Action URLs
    config.add_pypi_action_route("legacy.api.pypi.file_upload", "file_upload")
    config.add_pypi_action_route("legacy.api.pypi.submit", "submit")
    config.add_pypi_action_route(
        "legacy.api.pypi.submit_pkg_info",
        "submit_pkg_info",
    )
    config.add_pypi_action_route("legacy.api.pypi.doc_upload", "doc_upload")
    config.add_pypi_action_route("legacy.api.pypi.doap", "doap")

    # Legacy XMLRPC
    config.add_xmlrpc_endpoint(
        "pypi",
        pattern="/pypi",
        header="Content-Type:text/xml",
        factory=ReadOnly(),
    )

    # Legacy Documentation
    config.add_route("legacy.docs", config.registry.settings["docs.url"])

    # Legacy Redirects
    config.add_redirect("/pypi/{name}/", "/project/{name}/")
    config.add_redirect(
        "/pypi/{name}/{version}/",
        "/project/{name}/{version}/",
    )
