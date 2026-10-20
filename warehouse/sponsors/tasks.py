# SPDX-License-Identifier: Apache-2.0

from typing import TYPE_CHECKING
from urllib.parse import urlencode

import requests

from sqlalchemy import or_, true
from sqlalchemy.exc import NoResultFound

from warehouse import tasks
from warehouse.sponsors.models import Sponsor

if TYPE_CHECKING:
    from typing import NotRequired, TypedDict

    from pyramid.request import Request

    class LogoPlacement(TypedDict):
        sponsor: str
        sponsor_slug: str
        description: str
        sponsor_url: str
        logo: str
        white_logo: NotRequired[str | None]
        level_name: str
        level_order: int


@tasks.task(ignore_result=True, acks_late=True)
def update_pypi_sponsors(request):
    """
    Read data from pythondotorg's logo placement API and update Sponsors
    table to mirror it.
    """
    host = request.registry.settings["pythondotorg.host"]
    token = request.registry.settings["pythondotorg.api_token"]
    headers = {"Authorization": f"Token {token}"}

    sponsors_placements = _fetch_placements(host, headers, "sponsors")
    sidebar_placements = _fetch_placements(host, headers, "sidebar")

    # deactivate current PSF sponsors to keep it up to date with API
    request.db.query(Sponsor).filter(Sponsor.psf_sponsor == true()).update(
        {"psf_sponsor": False}
    )
    # reset API-managed flags, manual sponsors keep the ones set in the admin
    request.db.query(Sponsor).filter(Sponsor.origin == "remote").update(
        {"footer": False, "sidebar": False}
    )

    for sponsor_info in sponsors_placements:
        sponsor = _sync_sponsor(request, sponsor_info)
        if sponsor is None:
            continue
        sponsor.psf_sponsor = True
        sponsor.footer = sponsor_info["level_name"] in {"Visionary", "Sustainability"}

    for sponsor_info in sidebar_placements:
        sponsor = _sync_sponsor(request, sponsor_info)
        if sponsor is None:
            continue
        sponsor.sidebar = True


def _fetch_placements(
    host: str, headers: dict[str, str], flight: str
) -> list[LogoPlacement]:
    qs = urlencode({"publisher": "pypi", "flight": flight})
    url = f"{host}/api/v2/sponsors/logo-placement/?{qs}"
    response = requests.get(url, headers=headers, timeout=5)
    response.raise_for_status()
    return response.json()


def _sync_sponsor(request: Request, sponsor_info: LogoPlacement) -> Sponsor | None:
    """
    Create or update the sponsor described by one logo placement.
    """
    name = sponsor_info["sponsor"]
    slug = sponsor_info["sponsor_slug"]
    query = request.db.query(Sponsor)
    try:
        sponsor = query.filter(or_(Sponsor.name == name, Sponsor.slug == slug)).one()
        # infra and one-time sponsors are managed locally, never from the API
        if sponsor.infra_sponsor or sponsor.one_time:
            return None
    except NoResultFound:
        sponsor = Sponsor()
        request.db.add(sponsor)

    sponsor.name = name
    sponsor.slug = slug
    sponsor.service = sponsor_info["description"]
    sponsor.link_url = sponsor_info["sponsor_url"]
    sponsor.color_logo_url = sponsor_info["logo"]
    sponsor.white_logo_url = sponsor_info.get("white_logo")
    sponsor.level_name = sponsor_info["level_name"]
    sponsor.level_order = sponsor_info["level_order"]
    sponsor.is_active = True
    sponsor.origin = "remote"
    return sponsor
