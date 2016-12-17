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
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    warehouse = config.get_settings().get("warehouse.domain")
    files_url = config.get_settings()["files.url"]

    # Simple Route for health checks.
    config.add_route("health", "/_health/")

    # Basic global routes
    config.add_route("index", "/", domain=warehouse)
    config.add_route("robots.txt", "/robots.txt", domain=warehouse)
    config.add_route("opensearch.xml", "/opensearch.xml", domain=warehouse)
    config.add_route("index.sitemap.xml", "/sitemap.xml", domain=warehouse)
    config.add_route(
        "bucket.sitemap.xml",
        "/{bucket}.sitemap.xml",
        domain=warehouse,
    )

    # Some static, template driven pages
    config.add_template_view("help", "/help/", "pages/help.html")
    config.add_template_view("security", "/security/", "pages/security.html")
    config.add_template_view(
        "sponsors",
        "/sponsors/",
        # Use the full resource path here to make it able to be overridden by
        # pypi-theme.
        "warehouse:templates/pages/sponsors.html",
    )

    # Our legal policies
    config.add_policy("terms-of-use", "terms.md")

    # HTML Snippets for including into other pages.
    config.add_route(
        "includes.current-user-indicator",
        "/_includes/current-user-indicator/",
        domain=warehouse,
    )

    # Search Routes
    config.add_route("search", "/search/", domain=warehouse)

    # Accounts
    config.add_route(
        "accounts.profile",
        "/user/{username}/",
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
        domain=warehouse,
    )
    config.add_route("accounts.login", "/account/login/", domain=warehouse)
    config.add_route("accounts.logout", "/account/logout/", domain=warehouse)
    config.add_route(
        "accounts.register",
        "/account/register/",
        domain=warehouse,
    )

    # Packaging
    config.add_route(
        "packaging.project",
        "/project/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        domain=warehouse,
    )
    config.add_route(
        "packaging.release",
        "/project/{name}/{version}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        domain=warehouse,
    )
    config.add_route("packaging.file", files_url)

    # RSS
    config.add_route("rss.updates", "/rss/updates.xml", domain=warehouse)
    config.add_route("rss.packages", "/rss/packages.xml", domain=warehouse)

    # Legacy URLs
    config.add_route("legacy.api.simple.index", "/simple/", domain=warehouse)
    config.add_route(
        "legacy.api.simple.detail",
        "/simple/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/",
        read_only=True,
        domain=warehouse,
    )
    config.add_route(
        "legacy.api.json.project",
        "/pypi/{name}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
        domain=warehouse,
    )
    config.add_route(
        "legacy.api.json.release",
        "/pypi/{name}/{version}/json",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        read_only=True,
        domain=warehouse,
    )

    # Legacy Action URLs
    # TODO: We should probably add Warehouse routes for these that just error
    #       and direct people to use upload.pypi.io
    config.add_pypi_action_route(
        "legacy.api.pypi.file_upload",
        "file_upload",
        domain=warehouse,
    )
    config.add_pypi_action_route(
        "legacy.api.pypi.submit",
        "submit",
        domain=warehouse,
    )
    config.add_pypi_action_route(
        "legacy.api.pypi.submit_pkg_info",
        "submit_pkg_info",
        domain=warehouse,
    )
    config.add_pypi_action_route(
        "legacy.api.pypi.doc_upload",
        "doc_upload",
        domain=warehouse,
    )
    config.add_pypi_action_route(
        "legacy.api.pypi.doap",
        "doap",
        domain=warehouse,
    )
    config.add_pypi_action_route(
        "legacy.api.pypi.list_classifiers",
        "list_classifiers",
        domain=warehouse,
    )

    # Legacy XMLRPC
    config.add_xmlrpc_endpoint(
        "pypi",
        pattern="/pypi",
        header="Content-Type:text/xml",
        domain=warehouse,
    )

    # Legacy Documentation
    config.add_route("legacy.docs", config.registry.settings["docs.url"])

    # Legacy Redirects
    config.add_redirect("/pypi/{name}/", "/project/{name}/", domain=warehouse)
    config.add_redirect(
        "/pypi/{name}/{version}/",
        "/project/{name}/{version}/",
        domain=warehouse,
    )
    config.add_redirect("/packages/{path:.*}", files_url, domain=warehouse)

    # Legacy Action Redirects
    config.add_pypi_action_redirect(
        "rss",
        "/rss/updates.xml",
        domain=warehouse,
    )
    config.add_pypi_action_redirect(
        "packages_rss",
        "/rss/packages.xml",
        domain=warehouse,
    )
