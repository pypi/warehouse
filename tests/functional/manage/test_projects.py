# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.packaging.models import LifecycleStatus


class TestManageProjects:
    def test_segments_active_and_archived_projects(self, webtest, login_user):
        """
        The projects page lists active projects up top and archived
        projects in a separate, clearly labeled section underneath.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        active_project = ProjectFactory.create(name="active-project")
        RoleFactory.create(user=user, project=active_project, role_name="Owner")
        archived_project = ProjectFactory.create(
            name="archived-project", lifecycle_status=LifecycleStatus.Archived
        )
        RoleFactory.create(user=user, project=archived_project, role_name="Owner")
        login_user(user)

        projects_page = webtest.get("/manage/projects/", status=HTTPStatus.OK)

        assert "Active Projects" in projects_page.text
        assert "Archived Projects" in projects_page.text
        assert "active-project" in projects_page.text
        assert "archived-project" in projects_page.text

    def test_hides_archived_section_when_no_archived_projects(
        self, webtest, login_user
    ):
        """
        The "Archived Projects" section is omitted entirely for a user
        with no archived projects.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        active_project = ProjectFactory.create(name="only-active-project")
        RoleFactory.create(user=user, project=active_project, role_name="Owner")
        login_user(user)

        projects_page = webtest.get("/manage/projects/", status=HTTPStatus.OK)

        assert "Active Projects" in projects_page.text
        assert "Archived Projects" not in projects_page.text
