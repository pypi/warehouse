# SPDX-License-Identifier: Apache-2.0

import uuid

import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.macaroons import MacaroonFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
)
from tests.common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory
from warehouse.packaging.models import LifecycleStatus


def _csrf(webtest):
    fragment = webtest.get("/_includes/authed/current-user-indicator/")
    return next(
        form
        for form in fragment.forms.values()
        if form.action.endswith("/account/logout/")
    )["csrf_token"].value


@pytest.mark.parametrize(
    "role",
    [
        "is_security",
        "is_superuser",
        "is_support",
        "is_moderator",
        "is_psf_staff",
        "is_observer",
        None,
    ],
)
def test_report_access_and_controls(webtest, login_admin, make_malware_report, role):
    login_admin(**({role: True} if role else {"is_superuser": False}))
    report = make_malware_report()
    ReleaseFactory.create(project=report.related, version="1.0")
    allowed = role in {"is_security", "is_superuser", "is_support", "is_moderator"}
    destructive = role in {"is_security", "is_superuser"}
    expected = 200 if allowed else 403
    webtest.get("/admin/malware_reports/", status=expected)
    detail = webtest.get(f"/admin/malware_reports/{report.id}/", status=expected)
    webtest.get(
        f"/admin/projects/{report.related.normalized_name}/malware_reports/",
        status=expected,
    )
    if allowed:
        remove = detail.html.select_one('[data-target="#modal-remove-release"]')
        assert remove.has_attr("disabled") is not destructive
        assert not detail.html.select_one(
            '[data-target="#modal-not-malware"]'
        ).has_attr("disabled")
    else:
        fragment = webtest.get("/_includes/authed/current-user-indicator/")
        assert not fragment.html.select('a[href="/admin/malware_reports/"]')
    token = _csrf(webtest)
    webtest.post(
        f"/admin/malware_reports/{report.id}/not_malware/",
        {"csrf_token": token, "reason": "Reviewed"},
        status=303 if allowed else 403,
    )
    assert bool(report.actions) is allowed
    if not destructive:
        for action in ["remove_malware", "remove_release"]:
            webtest.post(
                f"/admin/malware_reports/{report.id}/{action}/",
                {"csrf_token": token},
                status=403,
            )


def test_security_removed_project_disables_project_actions(
    webtest, login_admin, make_malware_report
):
    login_admin(is_security=True)
    report = make_malware_report()
    report.related_id = None
    detail = webtest.get(f"/admin/malware_reports/{report.id}/")
    for action in ["quarantine-release", "quarantine", "remove-release"]:
        assert detail.html.select_one(f'[data-target="#modal-{action}"]').has_attr(
            "disabled"
        )
    for action in ["not-malware", "remove-malware"]:
        assert not detail.html.select_one(f'[data-target="#modal-{action}"]').has_attr(
            "disabled"
        )


def test_security_navigation_and_unrelated_writes(
    webtest, login_admin, make_malware_report
):
    login_admin(is_security=True)
    report = make_malware_report()
    project = report.related
    release = ReleaseFactory.create(project=project, version="1.0")
    owner = UserFactory.create()
    RoleFactory.create(user=owner, project=project, role_name="Owner")
    page = webtest.get("/admin/malware_reports/")
    assert {a["href"] for a in page.html.select(".nav-sidebar a")} == {
        "/admin/malware_reports/",
        "/admin/quarantine/",
        "/admin/projects/",
        "/admin/users/",
    }
    fragment = webtest.get("/_includes/authed/current-user-indicator/")
    assert fragment.html.select_one('a[href="/admin/malware_reports/"]')
    for path in [
        "/admin/",
        "/admin/organizations/",
        "/admin/observations/",
        "/admin/flags/",
        "/admin/token/decode",
    ]:
        webtest.get(path, status=403)
    for path in [
        f"/admin/projects/{project.normalized_name}/",
        f"/admin/projects/{project.normalized_name}/release/{release.version}",
        f"/admin/users/{owner.username}/",
        "/admin/quarantine/",
    ]:
        webtest.get(path, status=200)
    token = _csrf(webtest)
    for path in [
        f"/admin/users/{owner.username}/",
        f"/admin/projects/{project.normalized_name}/",
        f"/admin/projects/{project.normalized_name}/delete/",
        f"/admin/projects/{project.normalized_name}/release/{release.version}/delete/",
        f"/admin/projects/{project.normalized_name}/archive/",
    ]:
        webtest.post(
            path,
            {"csrf_token": token, "confirm_project_name": project.name},
            status=403,
        )
    assert release in project.releases
    assert not owner.is_frozen


@pytest.mark.parametrize(
    "action",
    [
        "",
        "add_helpscout_conversation/",
        "send_to_helpscout/",
        "not_malware/",
        "quarantine/",
        "quarantine_release/",
        "remove_malware/",
        "remove_release/",
    ],
)
@pytest.mark.parametrize("missing", [False, True])
def test_security_cannot_use_non_malware_observation_ids(
    webtest, login_admin, make_malware_report, action, missing
):
    login_admin(is_security=True)
    report = make_malware_report()
    report.kind = "is_spam"
    report_id = uuid.uuid4() if missing else report.id
    path = f"/admin/malware_reports/{report_id}/{action}"
    if action:
        webtest.post(path, {"csrf_token": _csrf(webtest)}, status=404)
    else:
        webtest.get(path, status=404)
    assert not report.actions
    assert report.related.lifecycle_status is None


def test_security_release_quarantine_and_clear(
    webtest, login_admin, make_malware_report
):
    login_admin(is_security=True)
    report = make_malware_report()
    project = report.related
    release = ReleaseFactory.create(project=project, version="1.0")
    token = _csrf(webtest)
    webtest.post(
        f"/admin/malware_reports/{report.id}/quarantine_release/",
        {"csrf_token": token, "versions": release.version},
        status=303,
    )
    assert release.lifecycle_status == LifecycleStatus.QuarantineEnter
    webtest.post(
        f"/admin/projects/{project.normalized_name}/release/{release.version}/remove_from_quarantine/",
        {"csrf_token": token, "confirm_project_name": project.name},
        status=303,
    )
    assert release.lifecycle_status == LifecycleStatus.QuarantineExit


def test_security_report_csrf(webtest, login_admin, make_malware_report):
    login_admin(is_security=True)
    report = make_malware_report()
    webtest.post(
        f"/admin/malware_reports/{report.id}/not_malware/",
        {"csrf_token": "invalid"},
        status=400,
    )
    assert not report.actions


@pytest.mark.parametrize(
    ("role", "full_navigation"),
    [
        ("is_security", False),
        ("is_superuser", True),
        ("is_support", True),
        ("is_moderator", True),
    ],
)
def test_contextual_navigation_uses_global_permissions(
    webtest, login_admin, role, full_navigation
):
    login_admin(**{role: True})
    target = UserFactory.create()
    organization = OrganizationFactory.create()
    OrganizationRoleFactory.create(user=target, organization=organization)
    project = ProjectFactory.create()
    OrganizationProjectFactory.create(organization=organization, project=project)
    token = MacaroonFactory.create(user_id=target.id)

    user_page = webtest.get(f"/admin/users/{target.username}/")
    project_page = webtest.get(f"/admin/projects/{project.normalized_name}/")
    organization_link = f'a[href="/admin/organizations/{organization.id}/"]'
    token_link = f'a[href="/admin/macaroons/{token.id}"]'
    assert bool(user_page.html.select("#api-tokens")) is full_navigation
    assert bool(user_page.html.select(token_link)) is (role == "is_superuser")
    for page in [user_page, project_page]:
        assert bool(page.html.select(organization_link)) is full_navigation
        assert page.html.select_one(".brand-link")["href"] == (
            "/admin/" if full_navigation else "/admin/malware_reports/"
        )
