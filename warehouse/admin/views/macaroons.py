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

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.events.tags import EventTag
from warehouse.macaroons.errors import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon
from warehouse.macaroons.services import deserialize_raw_macaroon


@view_config(
    route_name="admin.macaroon.decode_token",
    renderer="admin/macaroons/decode_token.html",
    permission="admin",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.macaroon.decode_token",
    renderer="admin/macaroons/decode_token.html",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def macaroon_decode_token(request):
    """
    This Admin page operates a little differently than others, since Tokens are
    not a Model, rather a logical construct that can lead to a Macaroon, or not.
    """
    if request.method != "POST":
        return {}

    token = request.POST.get("token")
    if not token:
        raise HTTPBadRequest("No token provided.")

    try:
        macaroon = deserialize_raw_macaroon(token)
    except InvalidMacaroonError as e:
        raise HTTPBadRequest("The token cannot be deserialized") from e

    # Try to find the database record for this macaroon
    macaroon_service = request.find_service(IMacaroonService, context=None)
    try:
        db_record = macaroon_service.find_from_raw(token)
    except InvalidMacaroonError:
        db_record = None

    return {"macaroon": macaroon, "db_record": db_record}


@view_config(
    route_name="admin.macaroon.detail",
    renderer="admin/macaroons/detail.html",
    permission="admin",
    uses_session=True,
)
def macaroon_detail(request):
    macaroon_id = request.matchdict["macaroon_id"]

    macaroon = (
        request.db.query(Macaroon)
        .filter(Macaroon.id == macaroon_id)
        .options(joinedload(Macaroon.user))
        .first()
    )

    if macaroon is None:
        raise HTTPNotFound()

    return {"macaroon": macaroon}


@view_config(
    route_name="admin.macaroon.delete",
    permission="admin",
    uses_session=True,
    require_methods=False,
)
def macaroon_delete(request):
    macaroon_id = request.matchdict["macaroon_id"]

    macaroon_service = request.find_service(IMacaroonService, context=None)
    macaroon = macaroon_service.find_macaroon(macaroon_id)

    # TODO: Shows up in user history. Should it? `removed_by` is not shown.
    # Since we still have a macaroon, record the event to the associated user
    macaroon.user.record_event(
        tag=EventTag.Account.APITokenRemoved,
        request=request,
        additional={
            "macaroon_id": str(macaroon.id),
            "description": macaroon.description,
            "removed_by": request.user.username,
        },
    )

    macaroon_service.delete_macaroon(macaroon_id)

    request.session.flash(
        f"Macaroon with ID {macaroon_id} has been deleted.", queue="success"
    )

    return HTTPSeeOther(request.route_path("admin.macaroon.decode_token"))
