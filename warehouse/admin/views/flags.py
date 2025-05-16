# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config

from warehouse.admin.flags import AdminFlag
from warehouse.authnz import Permissions


@view_config(
    route_name="admin.flags",
    renderer="admin/flags/index.html",
    permission=Permissions.AdminFlagsRead,
    request_method="GET",
    uses_session=True,
)
def get_flags(request):
    return {"flags": request.db.query(AdminFlag).order_by(AdminFlag.id).all()}


@view_config(
    route_name="admin.flags.edit",
    permission=Permissions.AdminFlagsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def edit_flag(request):
    flag = request.db.get(AdminFlag, request.POST["id"])
    flag.description = request.POST["description"]
    flag.enabled = bool(request.POST.get("enabled"))

    request.session.flash(f"Edited flag {flag.id!r}", queue="success")

    return HTTPSeeOther(request.route_path("admin.flags"))
