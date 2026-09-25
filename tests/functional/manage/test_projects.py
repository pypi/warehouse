# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory
from warehouse.packaging.models import LifecycleStatus, Project
from warehouse.utils.project import (
    DELETE_PROJECT_ACKNOWLEDGMENTS,
    DELETE_RELEASE_ACKNOWLEDGMENTS,
)


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

    def test_delete_project_requires_acknowledgments(self, webtest, login_user):
        """Submitting the delete form with unchecked boxes does not delete.

        The checkboxes used to be gated only by a ``disabled`` attribute on an
        anchor, which browsers ignore, so the form could be submitted without
        them.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="deleteme")
        RoleFactory.create(user=user, project=project, role_name="Owner")
        login_user(user)

        settings_page = webtest.get(
            f"/manage/project/{project.normalized_name}/settings/",
            status=HTTPStatus.OK,
        )
        delete_form = next(
            form
            for form in settings_page.forms.values()
            if "confirm_project_name" in form.fields
        )

        # The rendered form carries exactly the acknowledgments the view
        # enforces, so neither side can gain or lose one unnoticed.
        assert {
            field
            for field in delete_form.fields
            if field and field.startswith("acknowledge_")
        } == set(DELETE_PROJECT_ACKNOWLEDGMENTS)

        db_session = webtest.extra_environ["warehouse.db_session"]

        # Type the project name but leave every box unchecked.
        delete_form["confirm_project_name"] = project.name
        refused = delete_form.submit().follow(status=HTTPStatus.OK)

        assert refused.request.path.endswith(
            f"/manage/project/{project.normalized_name}/settings/"
        )
        assert (
            db_session.query(Project).filter(Project.name == project.name).count() == 1
        )

    def test_releases_page_delete_form_includes_acknowledgments(
        self, webtest, login_user
    ):
        """The releases-page delete modal submits what the view requires.

        The release delete view is reachable from two templates; a modal that
        omits the acknowledgments would reject every delete it submits.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="releasepage")
        RoleFactory.create(user=user, project=project, role_name="Owner")
        ReleaseFactory.create(project=project, version="1.2.3")
        login_user(user)

        releases_page = webtest.get(
            f"/manage/project/{project.normalized_name}/releases/",
            status=HTTPStatus.OK,
        )
        delete_form = next(
            form
            for form in releases_page.forms.values()
            if "confirm_delete_version" in form.fields
        )

        assert {
            field
            for field in delete_form.fields
            if field and field.startswith("acknowledge_")
        } == set(DELETE_RELEASE_ACKNOWLEDGMENTS)

    def test_release_page_delete_form_includes_acknowledgments(
        self, webtest, login_user
    ):
        """The release detail page wires up the acknowledgments too.

        Three templates render a delete modal against the two views that
        require acknowledgments; a modal that forgets them would reject every
        delete it submits.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="releasedetail")
        RoleFactory.create(user=user, project=project, role_name="Owner")
        release = ReleaseFactory.create(project=project, version="1.2.3")
        login_user(user)

        release_page = webtest.get(
            f"/manage/project/{project.normalized_name}/release/{release.version}/",
            status=HTTPStatus.OK,
        )
        delete_form = next(
            form
            for form in release_page.forms.values()
            if "confirm_delete_version" in form.fields
        )

        assert {
            field
            for field in delete_form.fields
            if field and field.startswith("acknowledge_")
        } == set(DELETE_RELEASE_ACKNOWLEDGMENTS)
