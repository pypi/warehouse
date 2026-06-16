# SPDX-License-Identifier: Apache-2.0

"""Admin Views related to Quarantine"""

from __future__ import annotations

import typing

from pyramid.view import view_config
from sqlalchemy import select

from warehouse.authnz import Permissions
from warehouse.packaging.models import LifecycleStatus, Project, Release

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
def quarantine_list(request: Request) -> dict[str, list]:
    """
    List all projects and releases currently in quarantine.

    Shows projects with lifecycle_status == 'quarantine-enter',
    ordered by lifecycle_status_changed (oldest first), alongside releases
    with the same status (excluding releases whose parent project is itself
    quarantined, to avoid double-listing).
    """
    project_stmt = (
        select(Project)
        .where(Project.lifecycle_status == LifecycleStatus.QuarantineEnter)
        .order_by(Project.lifecycle_status_changed.asc())
    )
    quarantined_projects = request.db.scalars(project_stmt).all()

    release_stmt = (
        select(Release)
        .join(Release.project)
        .where(Release.lifecycle_status == LifecycleStatus.QuarantineEnter)
        .where(
            Project.lifecycle_status.is_distinct_from(LifecycleStatus.QuarantineEnter)
        )
        .order_by(Release.lifecycle_status_changed.asc())
    )
    quarantined_releases = request.db.scalars(release_stmt).all()

    return {
        "quarantined_projects": quarantined_projects,
        "quarantined_releases": quarantined_releases,
    }
