# SPDX-License-Identifier: Apache-2.0

"""Admin Views for release gating."""

from __future__ import annotations

import typing

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from warehouse.authnz import Permissions
from warehouse.gating.interfaces import IGateService
from warehouse.gating.models import (
    BLOCKING_GATE_STATUSES,
    GateStatus,
    ReleaseGate,
)
from warehouse.packaging.models import Release

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@view_config(
    route_name="admin.gating.list",
    renderer="warehouse.admin:templates/admin/gating/list.html",
    permission=Permissions.AdminProjectsRead,
    request_method="GET",
    uses_session=True,
    require_methods=False,
)
def gating_list(request: Request) -> dict[str, list]:
    """
    List the gates currently withholding a release, oldest first.

    `failed` gates need an administrator: nothing else will resolve them.
    """
    stmt = (
        select(ReleaseGate)
        .options(joinedload(ReleaseGate.release).joinedload(Release.project))
        .where(ReleaseGate.status.in_(BLOCKING_GATE_STATUSES))
        .order_by(ReleaseGate.created.asc())
    )

    return {"gates": request.db.scalars(stmt).all()}


@view_config(
    route_name="admin.gating.bypass",
    permission=Permissions.AdminProjectsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def gating_bypass(request: Request) -> HTTPSeeOther:
    """
    Release a hold by administrator decision, publishing the release.

    Recorded as `bypassed` rather than `passed`, with the administrator's
    username, so the audit trail distinguishes a policy clearing a release from
    a person overriding one. The kind is not validated against a known set:
    gates are registered in code, so an unrecognized one matches no gate row.
    """
    kind = request.matchdict["kind"]

    release = request.db.get(Release, request.matchdict["release_id"])
    if release is None:
        raise HTTPNotFound

    gate_service = request.find_service(IGateService, context=None)
    gate = gate_service.resolve(
        release,
        kind,
        GateStatus.Bypassed,
        note=request.POST.get("note") or "Bypassed by an administrator",
        resolved_by=request.user.username,
    )

    if gate is None:
        raise HTTPNotFound

    request.session.flash(
        f"Bypassed {kind} gate on {release.project.name} {release.version}",
        queue="success",
    )

    return HTTPSeeOther(request.route_path("admin.gating.list"))
