# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from datetime import timedelta

from pyramid.request import Request

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.packaging.models import (
    JournalEntry,
    Project,
    Release,
    RoleInvitation,
    RoleInvitationStatus,
)

logger = logging.getLogger(__name__)


@tasks.task(ignore_result=True, acks_late=True)
def update_role_invitation_status(request):
    invites = (
        request.db.query(RoleInvitation)
        .filter(RoleInvitation.invite_status == RoleInvitationStatus.Pending)
        .all()
    )
    token_service = request.find_service(ITokenService, name="email")

    for invite in invites:
        try:
            token_service.loads(invite.token)
        except TokenExpired:
            invite.invite_status = RoleInvitationStatus.Expired


@tasks.task(ignore_result=True)
def delete_expired_releases(request: Request) -> None:
    # Get all of the projects that have `releases_expire_after_days` set.
    projects = (
        request.db.query(Project)
        .filter(Project.releases_expire_after_days.is_not(None))
        .all()
    )

    for project in projects:
        # Determine the cutoff date for this project.
        cutoff = request.current_datetime - timedelta(
            days=project.releases_expire_after_days
        )

        # Get all of the releases for this project that are older than the cutoff
        # and are not the last remaining release. We order them by creation
        # date so that we delete the oldest ones first.
        releases_to_delete = (
            request.db.query(Release)
            .filter(
                Release.project == project,
                Release.created < cutoff,
            )
            .order_by(Release.created.asc())
            .all()
        )

        # Ensure we don't delete the last remaining release
        if len(project.releases) - len(releases_to_delete) <= 0 and project.releases:
            # If we would delete all releases, keep the oldest one
            releases_to_delete.pop(0)

        for release in releases_to_delete:
            request.db.delete(release)
            request.db.add(
                JournalEntry(
                    name=release.project.name,
                    action="remove expired release",
                    version=release.version,
                    submitted_by=request.user,  # System user or a dedicated bot user
                )
            )
            logger.info(
                f"Deleted expired release {release.project.name}/{release.version}"
            )
