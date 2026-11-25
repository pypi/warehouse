# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config

from warehouse.api.maintainer import ApiKey, IApiKeyService
from warehouse.authnz import Permissions
from warehouse.email import send_api_key_compromised_email
from warehouse.events.tags import EventTag
from warehouse.manage.views.view_helpers import parse_uuid


@view_config(
    route_name="admin.api_key.revoke",
    permission=Permissions.AdminApiKeysWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def api_key_revoke(request):
    """Revoke a user's Maintainer API key, optionally emailing them why."""
    api_key_id = parse_uuid(request.matchdict["api_key_id"])
    api_key = request.db.get(ApiKey, api_key_id) if api_key_id else None
    if api_key is None:
        return HTTPNotFound()

    user = api_key.user
    redirect = HTTPSeeOther(
        request.route_path("admin.user.detail", username=user.username)
    )

    api_key_service = request.find_service(IApiKeyService, context=None)
    if not api_key_service.revoke(api_key.id):
        request.session.flash(
            f"Maintainer API key {api_key.name!r} was already revoked", queue="error"
        )
        return redirect

    reason = request.POST.get("reason", "").strip() or None
    additional = {
        "name": api_key.name,
        "api_key_id": str(api_key.id),
        "revoked_by": request.user.username,  # not displayed to the user
        "redact_ip": True,
    }
    if reason:
        additional["reason"] = reason
    user.record_event(
        tag=EventTag.Account.APIKeyRevoked, request=request, additional=additional
    )

    if request.POST.get("notify"):
        send_api_key_compromised_email(
            request, user, name=api_key.name, admin_initiated=True, reason=reason
        )

    request.session.flash(
        f"Maintainer API key {api_key.name!r} revoked", queue="success"
    )
    return redirect
