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
    # Basic global routes
    config.add_route("index", "/", read_only=True)
    config.add_route("robots.txt", "/robots.txt", read_only=True)
    config.add_route("index.sitemap.xml", "/sitemap.xml", read_only=True)
    config.add_route(
        "bucket.sitemap.xml",
        "/{bucket}.sitemap.xml",
        read_only=True,
    )

    # HTML Snippets for including into other pages.
    config.add_route(
        "includes.current-user-indicator",
        "/_includes/current-user-indicator/",
        read_only=True,
    )

    # Search Routes
    config.add_route("search", "/search/", read_only=True)

    # Accounts
    config.add_route(
        "accounts.profile",
        "/user/{username}/",
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
        read_only=True,
    )
    config.add_route("accounts.login", "/account/login/")
    config.add_route("accounts.logout", "/account/logout/")

    # Packaging
    config.add_route(
        "packaging.project",
        "/project/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
    )
    config.add_route(
        "packaging.release",
        "/project/{name}/{version}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        read_only=True,
    )
    config.add_route("packaging.file", "/packages/{path:.*}", read_only=True)

    # RSS
    config.add_route("rss.updates", "/rss/updates.xml", read_only=True)
    config.add_route("rss.packages", "/rss/packages.xml", read_only=True)

    # Legacy URLs
    config.add_route("legacy.api.simple.index", "/simple/", read_only=True)
    config.add_route(
        "legacy.api.simple.detail",
        "/simple/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/",
        read_only=True,
    )
    config.add_route(
        "legacy.api.json.project",
        "/pypi/{name}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
    )
    config.add_route(
        "legacy.api.json.release",
        "/pypi/{name}/{version}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        read_only=True,
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
        read_only=True,
    )

    # Legacy Documentation
    config.add_route("legacy.docs", config.registry.settings["docs.url"])

    # Legacy Redirects
    config.add_redirect("/pypi/{name}/", "/project/{name}/")
    config.add_redirect(
        "/pypi/{name}/{version}/",
        "/project/{name}/{version}/",
    )

    # Legacy Action Redirects
    config.add_pypi_action_redirect("rss", "/rss/updates.xml")
    config.add_pypi_action_redirect("packages_rss", "/rss/packages.xml")
