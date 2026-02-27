# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

import pretend

from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.accounts.models import User
from warehouse.manage.tasks import (
    delete_expired_releases,
    update_role_invitation_status,
)
from warehouse.packaging.models import (
    Description,
    JournalEntry,
    Project,
    Release,
    RoleInvitationStatus,
)

from ...common.db.packaging import ProjectFactory, RoleInvitationFactory, UserFactory


class TestUpdateInvitationStatus:
    def test_update_invitation_status(self, db_request):
        project = ProjectFactory.create()
        user = UserFactory.create()
        invite = RoleInvitationFactory(user=user, project=project)

        token_service = pretend.stub(loads=pretend.raiser(TokenExpired))
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_role_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == RoleInvitationStatus.Expired

    def test_no_updates(self, db_request):
        project = ProjectFactory.create()
        user = UserFactory.create()
        invite = RoleInvitationFactory(user=user, project=project)

        token_service = pretend.stub(loads=lambda token: {})
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_role_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == RoleInvitationStatus.Pending


class TestDeleteExpiredReleases:
    def test_delete_expired_releases(self, db_request):
        # Create a user to be the submitter
        user = User(username="test-user", name="", password="")
        db_request.db.add(user)

        # Create a project with releases_expire_after_days set to 90
        project = Project(name="test-project", releases_expire_after_days=90)
        db_request.db.add(project)

        # Create a release that is older than 90 days
        release_old = Release(
            project=project,
            version="1.0.0",
            canonical_version="1.0.0",
            created=datetime.now() - timedelta(days=100),
            description=Description(raw="", html="", rendered_by=""),
        )
        db_request.db.add(release_old)

        # Create a release that is newer than 90 days
        release_new = Release(
            project=project,
            version="2.0.0",
            canonical_version="2.0.0",
            created=datetime.now() - timedelta(days=10),
            description=Description(raw="", html="", rendered_by=""),
        )
        db_request.db.add(release_new)

        db_request.user = user
        db_request.current_datetime = datetime.now()

        delete_expired_releases(db_request)

        assert release_old in db_request.db.deleted
        assert release_new not in db_request.db.deleted
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(
                name=project.name,
                action="remove expired release",
                version=release_old.version,
            )
            .count()
            == 1
        )

    def test_delete_expired_releases_keep_last(self, db_request):
        # Create a user to be the submitter
        user = User(username="test-user", name="", password="")
        db_request.db.add(user)

        # Create a project with releases_expire_after_days set to 90
        project = Project(name="test-project", releases_expire_after_days=90)
        db_request.db.add(project)

        # Create a release that is older than 90 days
        release_old = Release(
            project=project,
            version="1.0.0",
            canonical_version="1.0.0",
            created=datetime.now() - timedelta(days=100),
            description=Description(raw="", html="", rendered_by=""),
        )
        db_request.db.add(release_old)

        db_request.user = user
        db_request.current_datetime = datetime.now()

        delete_expired_releases(db_request)

        assert release_old not in db_request.db.deleted
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(
                name=project.name,
                action="remove expired release",
                version=release_old.version,
            )
            .count()
            == 0
        )
