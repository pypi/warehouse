# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ipaddress
import typing

from datetime import UTC, datetime

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload

from warehouse.accounts.models import UserUniqueLogin
from warehouse.authnz import Permissions
from warehouse.ip_addresses.models import BanReason, IpAddress
from warehouse.rate_limiting import IRateLimiter
from warehouse.rate_limiting.interfaces import WindowStats
from warehouse.utils.paginate import paginate_url_factory

if typing.TYPE_CHECKING:
    from pyramid.request import Request


def _canonical_ip(request: Request) -> str:
    """The matched IP address in the form the 404 limiter keys on."""
    try:
        return str(ipaddress.ip_address(request.matchdict["ip_address"]))
    except ValueError:
        raise HTTPBadRequest("Invalid IP address.") from None


@view_config(
    route_name="admin.ip_address.list",
    renderer="warehouse.admin:templates/admin/ip_addresses/list.html",
    permission=Permissions.AdminIpAddressesRead,
    uses_session=True,
)
def ip_address_list(request: Request) -> dict[str, SQLAlchemyORMPage[IpAddress] | str]:
    # TODO: Add search functionality
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    ip_address_query = request.db.query(IpAddress).order_by(IpAddress.id)

    ip_addresses = SQLAlchemyORMPage(
        ip_address_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"ip_addresses": ip_addresses, "q": q}


@view_config(
    route_name="admin.ip_address.detail",
    renderer="warehouse.admin:templates/admin/ip_addresses/detail.html",
    permission=Permissions.AdminIpAddressesRead,
    uses_session=True,
)
def ip_address_detail(
    request: Request,
) -> dict[str, str | IpAddress | list[UserUniqueLogin] | list[WindowStats] | None]:
    ip = _canonical_ip(request)
    ip_address = request.db.query(IpAddress).filter_by(ip_address=ip).one_or_none()

    unique_logins = []
    if ip_address is not None:
        unique_logins = (
            request.db.query(UserUniqueLogin)
            .options(joinedload(UserUniqueLogin.user))
            .filter(UserUniqueLogin.ip_address == ip_address)
            .order_by(UserUniqueLogin.created.desc())
            .all()
        )

    # The 404 limiter keys on the address alone, so its state is shown even
    # when no IpAddress row exists. get_window_stats returns one entry per
    # configured limit (an empty list if Redis is down).
    ratelimiter = request.find_service(IRateLimiter, name="notfound.ip", context=None)

    return {
        "ip": ip,
        "ip_address": ip_address,
        "unique_logins": unique_logins,
        "notfound_ratelimits": ratelimiter.get_window_stats(ip),
    }


@view_config(
    route_name="admin.ip_address.ban",
    permission=Permissions.AdminIpAddressesWrite,
    request_method="POST",
    uses_session=True,
    require_methods=["POST"],
)
def ban_ip(request: Request):
    ip_address_str = request.matchdict["ip_address"]
    try:
        ip_address = (
            request.db.query(IpAddress).filter_by(ip_address=ip_address_str).one()
        )
    except NoResultFound:
        raise HTTPBadRequest("No matching IP Address found.")

    if ip_address.is_banned:
        request.session.flash(
            f"IP address {ip_address.ip_address} is already banned.", queue="warning"
        )
    else:
        ip_address.is_banned = True
        ip_address.ban_reason = BanReason.ADMINISTRATIVE
        ip_address.ban_date = datetime.now(UTC)
        request.session.flash(
            f"Banned IP address {ip_address.ip_address}", queue="success"
        )

    return HTTPSeeOther(
        request.route_path("admin.ip_address.detail", ip_address=ip_address.ip_address)
    )


@view_config(
    route_name="admin.ip_address.reset_notfound_ratelimit",
    permission=Permissions.AdminIpAddressesWrite,
    request_method="POST",
    uses_session=True,
    require_methods=["POST"],
)
def reset_notfound_ratelimit(request: Request):
    ip = _canonical_ip(request)
    ratelimiter = request.find_service(IRateLimiter, name="notfound.ip", context=None)
    ratelimiter.clear(ip)
    request.session.flash(f"Reset 404 rate limit for IP address {ip}", queue="success")

    return HTTPSeeOther(request.route_path("admin.ip_address.detail", ip_address=ip))


@view_config(
    route_name="admin.ip_address.unban",
    permission=Permissions.AdminIpAddressesWrite,
    request_method="POST",
    uses_session=True,
    require_methods=["POST"],
)
def unban_ip(request: Request):
    ip_address_str = request.matchdict["ip_address"]
    try:
        ip_address = (
            request.db.query(IpAddress).filter_by(ip_address=ip_address_str).one()
        )
    except NoResultFound:
        raise HTTPBadRequest("No matching IP Address found.")

    if not ip_address.is_banned:
        request.session.flash(
            f"IP address {ip_address.ip_address} is not banned.", queue="warning"
        )
    else:
        ip_address.is_banned = False
        ip_address.ban_reason = None
        ip_address.ban_date = None
        request.session.flash(
            f"Unbanned IP address {ip_address.ip_address}", queue="success"
        )

    return HTTPSeeOther(
        request.route_path("admin.ip_address.detail", ip_address=ip_address.ip_address)
    )
