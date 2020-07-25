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

# NOTE: warehouse.forklift is a temporary package, and it is assumed that it
#       will go away eventually, once we split forklift out into it's own
#       project.


def _help_url(request, **kwargs):
    warehouse_domain = request.registry.settings.get("warehouse.domain")
    return request.route_url("help", _host=warehouse_domain, **kwargs)


def includeme(config):
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    forklift = config.get_settings().get("forklift.domain")

    # Include our legacy action routing
    config.include(".action_routing")

    # Add the routes that we'll be using in Forklift.
    config.add_legacy_action_route(
        "forklift.legacy.file_upload", "file_upload", domain=forklift
    )
    config.add_legacy_action_route("forklift.legacy.submit", "submit", domain=forklift)
    config.add_legacy_action_route(
        "forklift.legacy.submit_pkg_info", "submit_pkg_info", domain=forklift
    )
    config.add_legacy_action_route(
        "forklift.legacy.doc_upload", "doc_upload", domain=forklift
    )

    config.add_route("forklift.legacy.redirect", "/legacy", domain=forklift)

    config.add_request_method(_help_url, name="help_url")

    if forklift:
        config.add_template_view(
            "forklift.index",
            "/",
            "upload.html",
            route_kw={"domain": forklift},
            view_kw={"has_translations": True},
        )

        # Any call to /legacy/ not handled by another route (e.g. no :action
        # URL parameter, or an invalid :action URL parameter) falls through to
        # this catch-all route.
        config.add_template_view(
            "forklift.legacy.invalid_request",
            "/legacy/",
            "upload.html",
            route_kw={"domain": forklift},
            view_kw={"has_translations": True},
        )
