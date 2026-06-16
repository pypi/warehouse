# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.authnz import Permissions
from warehouse.email import send_token_compromised_email_leak
from warehouse.events.tags import EventTag
from warehouse.macaroons.errors import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon
from warehouse.macaroons.services import deserialize_raw_macaroon


@view_config(
    route_name="admin.macaroon.decode_token",
    renderer="warehouse.admin:templates/admin/macaroons/decode_token.html",
    permission=Permissions.AdminMacaroonsInspect,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.macaroon.decode_token",
    renderer="warehouse.admin:templates/admin/macaroons/decode_token.html",
    permission=Permissions.AdminMacaroonsInspect,
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
        raise HTTPBadRequest(f"The token cannot be deserialized: {e!r}") from e

    # Try to find the database record for this macaroon
    macaroon_service = request.find_service(IMacaroonService, context=None)
    try:
        db_record = macaroon_service.find_from_raw(token)
    except InvalidMacaroonError:
        db_record = None

    return {"macaroon": macaroon, "db_record": db_record}


@view_config(
    route_name="admin.macaroon.detail",
    renderer="warehouse.admin:templates/admin/macaroons/detail.html",
    permission=Permissions.AdminMacaroonsRead,
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
        raise HTTPNotFound

    return {"macaroon": macaroon}


@view_config(
    route_name="admin.macaroon.delete",
    permission=Permissions.AdminMacaroonsWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def macaroon_delete(request):
    macaroon_id = request.matchdict["macaroon_id"]

    macaroon_service = request.find_service(IMacaroonService, context=None)
    macaroon = macaroon_service.find_macaroon(macaroon_id)
    if macaroon is None:
        raise HTTPNotFound

    user = macaroon.user
    notify = bool(request.POST.get("notify"))
    reason = request.POST.get("reason", "").strip() or None

    additional = {
        "macaroon_id": str(macaroon.id),
        "description": macaroon.description,
        "removed_by": request.user.username,  # not displayed to user
        "redact_ip": True,
    }
    if reason:
        additional["reason"] = reason

    # Since we still have a macaroon, record the event to the associated user
    user.record_event(
        tag=EventTag.Account.APITokenRemoved,
        request=request,
        additional=additional,
    )

    macaroon_service.delete_macaroon(macaroon_id)

    if notify:
        send_token_compromised_email_leak(
            request, user, admin_initiated=True, reason=reason
        )

    request.session.flash(
        f"Macaroon with ID {macaroon_id} has been deleted.", queue="success"
    )

    return HTTPSeeOther(request.route_path("admin.macaroon.decode_token"))
