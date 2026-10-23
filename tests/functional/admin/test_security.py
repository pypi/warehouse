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
from tests.common.db.ses import EmailMessageFactory
from warehouse.packaging.models import LifecycleStatus
from warehouse.utils.security_policy import principals_for


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


@pytest.mark.parametrize(
    "role", ["is_security", "is_superuser", "is_support", "is_moderator"]
)
def test_observations_navigation_keeps_existing_dropdown(webtest, login_admin, role):
    login_admin(**{role: True})
    page = webtest.get("/admin/malware_reports/")
    reports_link = page.html.select_one(
        '.nav-sidebar a[href="/admin/malware_reports/"]'
    )
    dropdown = reports_link.find_parent("ul", class_="nav-treeview")
    assert dropdown is not None
    assert {a["href"] for a in dropdown.select("a")} == {
        "/admin/malware_reports/",
        "/admin/quarantine/",
        "/admin/observers/reputation/",
        "/admin/observations/insights/",
        "/admin/observations/",
    }


@pytest.mark.parametrize(
    ("role", "can_set_limits"),
    [
        ("is_security", False),
        ("is_superuser", True),
        ("is_support", True),
        ("is_moderator", True),
    ],
)
def test_project_limit_controls_require_permission(
    webtest, login_admin, role, can_set_limits
):
    login_admin(**{role: True})
    project = ProjectFactory.create(
        upload_limit=256 * 1024**2, total_size_limit=32 * 1024**3
    )
    project_path = f"/admin/projects/{project.normalized_name}/"
    page = webtest.get(project_path)
    attributes = page.html.select_one("#attributes")
    assert "256.0 MiB" in attributes.get_text()
    assert "32.0 GiB" in attributes.get_text()
    for field in ["upload_limit", "total_size_limit"]:
        assert bool(attributes.select(f'input[name="{field}"]')) is can_set_limits
        assert (
            bool(attributes.select(f'form[action$="/set_{field}/"]')) is can_set_limits
        )
        if not can_set_limits:
            webtest.post(
                f"{project_path}set_{field}/",
                {"csrf_token": _csrf(webtest), field: "512"},
                status=403,
            )
    assert project.upload_limit == 256 * 1024**2
    assert project.total_size_limit == 32 * 1024**3


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
    assert {
        a["href"] for a in page.html.select(".nav-sidebar a") if a["href"] != "#"
    } == {
        "/admin/malware_reports/",
        "/admin/observations/",
        "/admin/observations/insights/",
        "/admin/observers/reputation/",
        "/admin/quarantine/",
        "/admin/projects/",
        "/admin/users/",
        "/admin/emails/",
    }
    fragment = webtest.get("/_includes/authed/current-user-indicator/")
    assert fragment.html.select_one('a[href="/admin/malware_reports/"]')
    for path in [
        "/admin/",
        "/admin/organizations/",
        "/admin/flags/",
        "/admin/token/decode",
    ]:
        webtest.get(path, status=403)
    for path in [
        f"/admin/projects/{project.normalized_name}/",
        f"/admin/projects/{project.normalized_name}/release/{release.version}",
        f"/admin/users/{owner.username}/",
        "/admin/quarantine/",
        "/admin/observations/",
        "/admin/observations/insights/",
        "/admin/observers/reputation/",
        "/admin/emails/",
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


def test_security_can_add_project_and_release_observations(webtest, login_admin):
    reviewer = login_admin(is_security=True)
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project, version="1.0")
    project_path = f"/admin/projects/{project.normalized_name}/"
    db = webtest.extra_environ["warehouse.db_session"]
    for resource, path, kind in [
        (project, project_path, "is_malware"),
        (
            release,
            f"{project_path}release/{release.version}",
            "is_dependency_confusion",
        ),
    ]:
        page = webtest.get(path)
        action = page.html.select_one("#addObservationModal form")["action"]
        form = next(form for form in page.forms.values() if form.action == action)
        form["kind"] = kind
        form["summary"] = "Investigation evidence recorded by a security reviewer."
        form.submit(status=303)
        observation = (
            db.query(resource.Observation).filter_by(related_id=resource.id).one()
        )
        assert observation.kind == kind
        assert observation.summary == form["summary"].value
        assert observation.observer == reviewer.observer
        assert "/admin/observations/" in {
            link["href"] for link in page.html.select(".nav-sidebar a")
        }
    observations_link = webtest.get(project_path).html.select_one(
        '#project_observations a[href$="/observations/"]'
    )
    observations = webtest.get(observations_link["href"])
    assert (
        "Investigation evidence recorded by a security reviewer." in observations.text
    )


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
def test_email_log_access_is_read_only_for_security(webtest, login_admin, role):
    login_admin(**({role: True} if role else {"is_superuser": False}))
    target = UserFactory.create(with_verified_primary_email=True)
    message = EmailMessageFactory.create(
        to=target.primary_email.email, subject="Security triage correspondence"
    )
    unrelated = EmailMessageFactory.create(subject="Unrelated correspondence")
    allowed = role in {"is_security", "is_superuser", "is_support", "is_moderator"}
    expected = 200 if allowed else 403
    listing = webtest.get("/admin/emails/", status=expected)
    detail = webtest.get(f"/admin/emails/{message.id}/", status=expected)
    if allowed:
        assert message.message_id in detail.text
        assert message.to in detail.text
        assert bool(listing.html.select('form[action="/admin/emails/mass/"]')) is (
            role == "is_superuser"
        )
        user_page = webtest.get(f"/admin/users/{target.username}/")
        assert user_page.html.select_one('.nav-sidebar a[href="/admin/emails/"]')
        search_link = user_page.html.select_one(
            '.content-wrapper a[href^="/admin/emails/?"]'
        )
        search = webtest.get(search_link["href"])
        assert message.subject in search.text
        assert unrelated.subject not in search.text
    if role != "is_superuser":
        webtest.post(
            "/admin/emails/mass/",
            {"csrf_token": _csrf(webtest)},
            status=403,
        )


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


@pytest.mark.parametrize(
    "role", ["is_security", "is_support", "is_moderator", "is_superuser"]
)
def test_security_assignment_requires_superuser(webtest, login_admin, role):
    login_admin(**{role: True})
    target = UserFactory.create()
    path = f"/admin/users/{target.username}/"
    token = _csrf(webtest)
    webtest.post(
        path,
        {"csrf_token": token, "is_active": "y", "is_security": "y"},
        status=303 if role == "is_superuser" else 403,
    )
    assert target.is_security is (role == "is_superuser")
    if role == "is_superuser":
        assert "group:security" in principals_for(target)
        webtest.post(path, {"csrf_token": token, "is_active": "y"}, status=303)
        assert "group:security" not in principals_for(target)


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
