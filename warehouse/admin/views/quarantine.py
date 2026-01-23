# SPDX-License-Identifier: Apache-2.0

"""Admin Views related to Quarantine"""

from __future__ import annotations

import typing

from pyramid.view import view_config
from sqlalchemy import select

from warehouse.authnz import Permissions
from warehouse.packaging.models import LifecycleStatus, Project

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@view_config(
    route_name="admin.quarantine.list",
    renderer="warehouse.admin:templates/admin/quarantine/list.html",
    permission=Permissions.AdminProjectsRead,
    request_method="GET",
    uses_session=True,
    require_methods=False,
)
def quarantine_list(request: Request) -> dict[str, list[Project]]:
    """
    List all projects currently in quarantine.

    Shows projects with lifecycle_status == 'quarantine-enter',
    ordered by lifecycle_status_changed (oldest first).
    """
    stmt = (
        select(Project)
        .where(Project.lifecycle_status == LifecycleStatus.QuarantineEnter)
        .order_by(Project.lifecycle_status_changed.asc())
    )

    quarantined_projects = request.db.scalars(stmt).all()

    return {"quarantined_projects": quarantined_projects}
