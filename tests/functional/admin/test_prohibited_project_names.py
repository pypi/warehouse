# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import OrganizationFactory, OrganizationRoleFactory
from tests.common.db.packaging import ProhibitedProjectFactory
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging.models import Project


class TestReleaseProhibitedProjectName:
    def test_release_to_organization_redirects_to_project_detail(
        self, webtest, login_user
    ):
        """
        Releasing a prohibited name to an organization returns a 303 to the new
        project's admin detail page, and following that redirect resolves (the
        project is committed before the browser follows it, so it is not a 404).
        """
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        login_user(admin)

        organization = OrganizationFactory.create(name="release-org")
        OrganizationRoleFactory.create(organization=organization, user=admin)
        ProhibitedProjectFactory.create(name="releasable")

        list_page = webtest.get(
            "/admin/prohibited_project_names/", status=HTTPStatus.OK
        )
        csrf_token = list_page.html.find("input", {"name": "csrf_token"})["value"]

        response = webtest.post(
            "/admin/prohibited_project_names/release/",
            {
                "csrf_token": csrf_token,
                "project_name": "releasable",
                "organization_name": "release-org",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        assert response.headers["Location"].endswith("/admin/projects/releasable/")

        detail_page = response.follow(status=HTTPStatus.OK)
        assert "releasable" in detail_page.text

        db_sess = webtest.extra_environ["warehouse.db_session"]
        project = db_sess.query(Project).filter(Project.name == "releasable").one()
        assert (
            db_sess.query(OrganizationProject)
            .filter(
                OrganizationProject.organization == organization,
                OrganizationProject.project == project,
            )
            .count()
            == 1
        )

    def test_release_error_redirects_to_list(self, webtest, login_user):
        """
        An error path (here, an unknown organization) returns a 303 whose target
        is the list page, not the POST-only release route. Following it resolves
        (200) rather than 404, and the flashed error is shown.
        """
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        login_user(admin)

        ProhibitedProjectFactory.create(name="releasable")

        list_page = webtest.get(
            "/admin/prohibited_project_names/", status=HTTPStatus.OK
        )
        csrf_token = list_page.html.find("input", {"name": "csrf_token"})["value"]

        response = webtest.post(
            "/admin/prohibited_project_names/release/",
            {
                "csrf_token": csrf_token,
                "project_name": "releasable",
                "organization_name": "does-not-exist",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        assert response.headers["Location"].endswith("/admin/prohibited_project_names/")

        followed = response.follow(status=HTTPStatus.OK)
        assert "Unknown organization 'does-not-exist'" in followed.html.get_text()
