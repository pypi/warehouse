# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from tests.common.db.accounts import (
    EmailFactory,
    OAuthAccountAssociationFactory,
    UserFactory,
)
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationNameCatalogFactory,
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
    EmailFactory.create(user=application.submitted_by)
    for email in ("approved", "declined", "moreinformationneeded"):
        mocker.patch(
            f"warehouse.organizations.services.send_new_organization_{email}_email"
        )

    detail_url = f"{APPLICATIONS}{application.id}/"
    detail = webtest.get(detail_url, status=HTTPStatus.OK)
    form = next(
        form for form in detail.forms.values() if form.action.endswith(f"/{action}/")
    )
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


def test_unreachable_applicant_blocks_information_requests(webtest, login_admin):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create(link_url="https://acme.com")
    EmailFactory.create(
        user=application.submitted_by, email="jdoe@acme.com", verified=False
    )

    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)

    banner = detail.html.select_one(".alert-danger")
    assert "You can't reach this applicant" in banner.text
    assert "jdoe@acme.com" in banner.text
    request_info = detail.html.select_one('[data-target="#requestMoreInfoModal"]')
    assert request_info.has_attr("disabled")
    assert detail.html.select(".org-review-check-ask") == []


def test_gitlab_application_suggests_gitlab_reply(webtest, login_admin):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create(
        link_url="https://gitlab.com/acme"
    )
    EmailFactory.create(user=application.submitted_by)
    OAuthAccountAssociationFactory.create(
        user=application.submitted_by, service="gitlab", external_username="jdoe"
    )

    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)

    asks = [ask["data-template"] for ask in detail.html.select(".org-review-check-ask")]
    assert "GitLabAssociationTemplate" in asks
    reply = detail.html.select_one("#GitLabAssociationTemplate")
    assert "GitLab group or project" in reply.text
    assert "https://gitlab.com/acme" in reply.text
    assert detail.html.select_one('a[href="https://gitlab.com/jdoe"]') is not None


def test_reviewer_edits_application(webtest, login_admin):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create(link_url="https://example.com")
    detail_url = f"{APPLICATIONS}{application.id}/"
    detail = webtest.get(detail_url, status=HTTPStatus.OK)
    form = detail.forms["editModalForm"]
    form["display_name"] = "Reviewed organization"
    form.submit(status=HTTPStatus.SEE_OTHER).follow(status=HTTPStatus.OK)
    assert application.display_name == "Reviewed organization"


def test_reviewer_previews_information_request(webtest, login_admin, mocker):
    login_admin(is_org_application_reviewer=True)
    send = mocker.patch("warehouse.email._send_email_to_user")
    application = OrganizationApplicationFactory.create(name="example")
    detail_url = f"{APPLICATIONS}{application.id}/"
    detail = webtest.get(detail_url, status=HTTPStatus.OK)

    preview = webtest.post(
        f"{detail_url}requestmoreinfo/preview/",
        {
            "csrf_token": detail.forms["editModalForm"]["csrf_token"].value,
            "message": "First ask.\r\n\r\nSecond ask.",
        },
        status=HTTPStatus.OK,
    ).json

    assert "'example'" in preview["subject"]
    assert "First ask.\r\n\r\nSecond ask." in preview["body"]
    assert f"/manage/organizations/application/{application.id}/" in preview["body"]
    # A preview never sends, and never changes the application.
    send.assert_not_called()
    assert application.status == OrganizationApplicationStatus.Submitted
    assert application.observations == []


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
        "requestmoreinfo/preview/",
        "addnote/",
    ):
        webtest.post(
            detail_url + action,
            {"csrf_token": csrf, "message": "Not authorized"},
            status=HTTPStatus.FORBIDDEN,
        )
    assert application.status == OrganizationApplicationStatus.Submitted
    assert application.observations == []


def test_withdrawn_application_is_read_only(webtest, login_admin):
    login_admin(is_org_application_reviewer=True)
    application = OrganizationApplicationFactory.create(
        status=OrganizationApplicationStatus.Withdrawn
    )
    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)
    for target in ("approve", "requestMoreInfo", "decline", "defer", "edit"):
        assert detail.html.select_one(f'[data-target="#{target}Modal"]').has_attr(
            "disabled"
        )


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


@pytest.mark.parametrize("role", ["is_superuser", "is_org_application_reviewer"])
def test_approve_with_deleted_organization_name(webtest, login_admin, mocker, role):
    login_admin(**{role: True})
    application = OrganizationApplicationFactory.create()
    EmailFactory.create(user=application.submitted_by)
    mocker.patch(
        "warehouse.organizations.services.send_new_organization_approved_email"
    )
    OrganizationNameCatalogFactory.create(
        normalized_name=application.normalized_name, organization_id=None
    )
    detail = webtest.get(f"{APPLICATIONS}{application.id}/", status=HTTPStatus.OK)
    assert "Name held by a deleted organization" in detail.text
    approve = next(
        form for form in detail.forms.values() if form.action.endswith("/approve/")
    )

    if role == "is_org_application_reviewer":
        assert "claim_orphaned_name" not in approve.fields
        webtest.post(
            approve.action,
            {
                "csrf_token": approve["csrf_token"].value,
                "claim_orphaned_name": "true",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        assert application.status == OrganizationApplicationStatus.Submitted
        return

    approve["claim_orphaned_name"].checked = True
    approve.submit(status=HTTPStatus.SEE_OTHER)
    assert application.status == OrganizationApplicationStatus.Approved


def test_locked_names_page(webtest, login_admin):
    login_admin(is_superuser=True)
    application = OrganizationApplicationFactory.create()
    OrganizationNameCatalogFactory.create(
        normalized_name=application.normalized_name, organization_id=None
    )

    page = webtest.get("/admin/organization_names/", status=HTTPStatus.OK)

    assert page.html.select_one(f'a[href$="/{application.id}/"]')
