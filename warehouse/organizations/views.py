# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config

from warehouse.cache.origin import origin_cache
from warehouse.organizations.models import Organization


@view_config(
    route_name="organizations.profile",
    context=Organization,
    renderer="warehouse:templates/organizations/profile.html",
    decorator=[
        origin_cache(1 * 24 * 60 * 60, stale_if_error=1 * 24 * 60 * 60)  # 1 day each.
    ],
    has_translations=True,
)
def profile(organization, request):
    if organization.name != request.matchdict.get("organization", organization.name):
        return HTTPMovedPermanently(
            request.current_route_path(organization=organization.name)
        )

    if organization.is_active:
        return {"organization": organization}
    raise HTTPNotFound()
