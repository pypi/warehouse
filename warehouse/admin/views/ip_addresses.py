# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound

from warehouse.accounts.models import UserUniqueLogin
from warehouse.authnz import Permissions
from warehouse.ip_addresses.models import IpAddress
from warehouse.utils.paginate import paginate_url_factory

if typing.TYPE_CHECKING:
    from pyramid.request import Request


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
def ip_address_detail(request: Request) -> dict[str, IpAddress]:
    ip_address = request.matchdict["ip_address"]
    try:
        ip_address = request.db.query(IpAddress).filter_by(ip_address=ip_address).one()
    except NoResultFound:
        raise HTTPBadRequest("No matching IP Address found.")

    unique_logins = (
        request.db.query(UserUniqueLogin)
        .filter(UserUniqueLogin.ip_address == str(ip_address.ip_address))
        .all()
    )

    return {"ip_address": ip_address, "unique_logins": unique_logins}
