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
from __future__ import annotations

import typing

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound

from warehouse.authnz import Permissions
from warehouse.ip_addresses.models import IpAddress
from warehouse.utils.paginate import paginate_url_factory

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@view_config(
    route_name="admin.ip_address.list",
    renderer="admin/ip_addresses/list.html",
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
    renderer="admin/ip_addresses/detail.html",
    permission=Permissions.AdminIpAddressesRead,
    uses_session=True,
)
def ip_address_detail(request: Request) -> dict[str, IpAddress]:
    ip_address_id = request.matchdict["ip_address_id"]
    try:
        ip_address = request.db.query(IpAddress).filter_by(id=ip_address_id).one()
    except NoResultFound:
        raise HTTPBadRequest("No IP Address found with that id.")

    return {"ip_address": ip_address}
