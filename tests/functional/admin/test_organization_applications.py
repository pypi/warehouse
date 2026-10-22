# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
)
from tests.common.db.packaging import ProjectFactory
from warehouse.organizations.models import OrganizationApplicationStatus

APPLICATIONS = "/admin/organization_applications/"


@pytest.mark.parametrize(
    "role", ["is_org_application_reviewer", "is_superuser", "is_support"]
)
@pytest.mark.parametrize(
    ("action", "status"),
    [
        ("approve", OrganizationApplicationStatus.Approved),
        ("decline", OrganizationApplicationStatus.Declined),
        ("defer", OrganizationApplicationStatus.Deferred),
        ("requestmoreinfo", OrganizationApplicationStatus.MoreInformationNeeded),
        ("addnote", OrganizationApplicationStatus.Submitted),
    ],
)
def test_review_actions(webtest, login_admin, mocker, role, action, status):
    reviewer = login_admin(**{role: True})
    application = OrganizationApplicationFactory.create()
    for email in ("approved", "declined", "moreinformationneeded"):
        mocker.patch(
            f"warehouse.organizations.services.send_new_organization_{email}_email"
        )

    detail_url = f"{APPLICATIONS}{application.id}/"
    detail = webtest.get(detail_url, status=HTTPStatus.OK)
    form = next(
        form for form in detail.forms.values() if form.action.endswith(f"/{action}/")
    )
    if "message" in form.fields:
        form["message"] = "Reviewed application"
    response = form.submit(status=HTTPStatus.SEE_OTHER)
    response.follow(status=HTTPStatus.OK)

    assert application.status == status
    if action == "approve":
        assert application.organization.owners == [application.submitted_by]
        if role == "is_org_application_reviewer":
            assert response.location.endswith(detail_url)
    elif action in {"addnote", "requestmoreinfo"}:
        observation = application.observations[0]
        assert observation.payload == {"message": "Reviewed application"}
        assert observation.observer.parent == reviewer
        assert observation.kind == (
            "admin_note" if action == "addnote" else "information_request"
        )


def test_reviewer_edits_application(webtest, login_admin):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create(link_url="https://example.com")
    detail_url = f"{APPLICATIONS}{application.id}/"
    detail = webtest.get(detail_url, status=HTTPStatus.OK)
    form = detail.forms["editModalForm"]
    form["display_name"] = "Reviewed organization"
    form.submit(status=HTTPStatus.SEE_OTHER).follow(status=HTTPStatus.OK)
    assert application.display_name == "Reviewed organization"


def test_reviewer_navigation_and_unrelated_access(webtest, login_admin):
    reviewer = login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create()
    organization = OrganizationFactory.create()
    project = ProjectFactory.create()
    target = UserFactory.create()

    home = webtest.get(
        "/_includes/authed/current-user-indicator/", status=HTTPStatus.OK
    )
    assert home.html.select_one(f'a.dropdown__link[href="{APPLICATIONS}"]')
    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)
    admin_links = {link["href"] for link in detail.html.select('a[href^="/admin/"]')}
    assert admin_links
    assert all(link.startswith(APPLICATIONS) for link in admin_links)
    listing = webtest.get(APPLICATIONS, status=HTTPStatus.OK)
    assert listing.html.select_one(f'a[href="{APPLICATIONS}{application.id}/"]')

    for path in (
        "/admin/",
        "/admin/organizations/",
        f"/admin/organizations/{organization.id}/",
        "/admin/users/",
        f"/admin/users/{reviewer.username}/",
        f"/admin/users/{target.username}/",
        f"/admin/users/{target.username}/export/",
        "/admin/projects/",
        f"/admin/projects/{project.normalized_name}/",
        "/admin/flags/",
        "/admin/banners/",
        "/admin/sponsors/",
    ):
        webtest.get(path, status=HTTPStatus.FORBIDDEN)

    csrf = detail.forms["editModalForm"]["csrf_token"].value
    for path in (
        f"/admin/organizations/{organization.id}/",
        f"/admin/organizations/{organization.id}/add_role/",
        f"/admin/organizations/{organization.id}/add_manual_activation/",
        f"/admin/organizations/{organization.id}/set_upload_limit/",
        f"/admin/users/{target.username}/",
    ):
        webtest.post(path, {"csrf_token": csrf}, status=HTTPStatus.FORBIDDEN)


@pytest.mark.parametrize("role", ["is_moderator", "is_psf_staff", "is_observer"])
def test_other_roles_cannot_review(webtest, login_admin, role):
    login_admin(**{role: True})
    application = OrganizationApplicationFactory.create()
    detail_url = f"{APPLICATIONS}{application.id}/"
    if role == "is_moderator":
        detail = webtest.get(detail_url, status=HTTPStatus.OK)
        csrf = detail.forms["editModalForm"]["csrf_token"].value
        assert detail.html.select_one('[data-target="#approveModal"]').has_attr(
            "disabled"
        )
        assert not detail.html.select_one("#editModalButton")
    else:
        webtest.get(APPLICATIONS, status=HTTPStatus.FORBIDDEN)
        webtest.get(detail_url, status=HTTPStatus.FORBIDDEN)
        home = webtest.get(
            "/_includes/authed/current-user-indicator/", status=HTTPStatus.OK
        )
        csrf = next(
            form["csrf_token"].value
            for form in home.forms.values()
            if form.action.endswith("/account/logout/")
        )
    for action in (
        "",
        "approve/",
        "decline/",
        "defer/",
        "requestmoreinfo/",
        "addnote/",
    ):
        webtest.post(
            detail_url + action,
            {"csrf_token": csrf, "message": "Not authorized"},
            status=HTTPStatus.FORBIDDEN,
        )
    assert application.status == OrganizationApplicationStatus.Submitted
    assert application.observations == []


@pytest.mark.parametrize("has_next", [False, True])
def test_reviewer_turbo_stays_in_applications(webtest, login_admin, has_next):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create()
    next_application = OrganizationApplicationFactory.create() if has_next else None
    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)
    form = next(
        form for form in detail.forms.values() if form.action.endswith("/defer/")
    )
    form["organization_applications_turbo_mode"] = "true"
    response = form.submit(status=HTTPStatus.SEE_OTHER)
    expected = f"{APPLICATIONS}{next_application.id}/" if has_next else APPLICATIONS
    assert response.location.endswith(expected)
    response.follow(status=HTTPStatus.OK)
    assert application.status == OrganizationApplicationStatus.Deferred


@pytest.mark.parametrize("role", ["is_superuser", "is_support", "is_moderator"])
def test_reviewer_role_assignment_requires_superuser(webtest, login_admin, role):
    login_admin(**{role: True})
    target = UserFactory.create()
    user_url = f"/admin/users/{target.username}/"
    detail = webtest.get(user_url, status=HTTPStatus.OK)
    form = next(
        form
        for form in detail.forms.values()
        if "is_org_application_reviewer" in form.fields
    )
    assert target.is_org_application_reviewer is False
    if role != "is_superuser":
        webtest.post(
            user_url,
            {
                "csrf_token": form["csrf_token"].value,
                "is_org_application_reviewer": "y",
            },
            status=HTTPStatus.FORBIDDEN,
        )
        assert target.is_org_application_reviewer is False
        return

    for enabled in (True, False):
        form["is_org_application_reviewer"] = enabled
        detail = form.submit(status=HTTPStatus.SEE_OTHER).follow(status=HTTPStatus.OK)
        assert target.is_org_application_reviewer is enabled
        assert ("group:org_application_reviewers" in target.__principals__()) is enabled
        form = next(
            form
            for form in detail.forms.values()
            if "is_org_application_reviewer" in form.fields
        )


@pytest.mark.parametrize("page", ["user", "project"])
def test_superuser_navigation_on_resource_pages(webtest, login_admin, page):
    # User and project pages authorize against their own ACLs; site navigation
    # must still reflect site-wide permissions there.
    admin = login_admin()
    project = ProjectFactory.create()
    path = (
        f"/admin/users/{admin.username}/"
        if page == "user"
        else f"/admin/projects/{project.normalized_name}/"
    )
    response = webtest.get(path, status=HTTPStatus.OK)
    sidebar = {link["href"] for link in response.html.select("aside.main-sidebar a")}
    assert response.html.select_one("a.brand-link")["href"] == "/admin/"
    assert {
        f"{APPLICATIONS}?q=is%3Asubmitted",
        "/admin/banners/",
        "/admin/sponsors/",
        f"/admin/users/{admin.username}/",
    } <= sidebar
    assert response.html.select_one('.breadcrumb a[href="/admin/"]')
