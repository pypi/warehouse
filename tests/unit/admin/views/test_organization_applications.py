# SPDX-License-Identifier: Apache-2.0
import datetime as dt
import uuid

from types import SimpleNamespace

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from sqlalchemy import update
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationNameCatalogFactory,
)
from tests.common.db.packaging import RoleFactory
from warehouse.admin.views import organizations as views
from warehouse.organizations import services
from warehouse.organizations.checks import CheckStatus
from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationNameCatalog,
    OrganizationType,
)


def _organization_application_routes(
    route_name, organization_application_id=None, organization_id=None
):
    if route_name == "admin.organization_application.detail":
        return f"/admin/organization_applications/{organization_application_id}/"
    if route_name == "admin.organization.detail":
        return f"/admin/organizations/{organization_id}/"
    if route_name == "admin.dashboard":
        return "/admin/"
    if route_name == "admin.organization_name.list":
        return "/admin/organization_names/"
    pytest.fail(f"No dummy route found for {route_name}")


class TestOrganizationApplicationList:
    def test_no_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(30),
            key=lambda o: o.submitted,
        )
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": organization_applications,
            "query": "",
            "terms": [],
        }

    def test_basic_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = organization_applications[0].name
        result = views.organization_applications_list(db_request)

        assert organization_applications[0] in result["organization_applications"]
        assert result["query"] == organization_applications[0].name
        assert result["terms"] == [organization_applications[0].name]

    def test_name_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = f"name:{organization_applications[0].name}"
        result = views.organization_applications_list(db_request)

        assert organization_applications[0] in result["organization_applications"]
        assert result["query"] == f"name:{organization_applications[0].name}"
        assert result["terms"] == [f"name:{organization_applications[0].name}"]

    def test_organization_application_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = (
            f"organization:{organization_applications[0].display_name}"
        )
        result = views.organization_applications_list(db_request)

        assert organization_applications[0] in result["organization_applications"]
        assert (
            result["query"]
            == f"organization:{organization_applications[0].display_name}"
        )
        assert result["terms"] == [
            f"organization:{organization_applications[0].display_name}"
        ]

    def test_url_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = f"url:{organization_applications[0].link_url}"
        result = views.organization_applications_list(db_request)

        assert organization_applications[0] in result["organization_applications"]
        assert result["query"] == f"url:{organization_applications[0].link_url}"
        assert result["terms"] == [f"url:{organization_applications[0].link_url}"]

    def test_description_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = (
            f"description:'{organization_applications[0].description}'"
        )
        result = views.organization_applications_list(db_request)

        assert organization_applications[0] in result["organization_applications"]
        assert (
            result["query"]
            == f"description:'{organization_applications[0].description}'"
        )
        assert result["terms"] == [
            f"description:{organization_applications[0].description}"
        ]

    def test_is_approved_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        organization_applications[0].status = OrganizationApplicationStatus.Approved
        organization_applications[1].status = OrganizationApplicationStatus.Approved
        organization_applications[2].status = OrganizationApplicationStatus.Declined
        organization_applications[3].status = OrganizationApplicationStatus.Submitted
        organization_applications[4].status = OrganizationApplicationStatus.Submitted
        db_request.GET["q"] = "is:approved"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": organization_applications[:2],
            "query": "is:approved",
            "terms": ["is:approved"],
        }

    def test_is_declined_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        organization_applications[0].status = OrganizationApplicationStatus.Approved
        organization_applications[1].status = OrganizationApplicationStatus.Approved
        organization_applications[2].status = OrganizationApplicationStatus.Declined
        organization_applications[3].status = OrganizationApplicationStatus.Submitted
        organization_applications[4].status = OrganizationApplicationStatus.Submitted
        db_request.GET["q"] = "is:declined"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": organization_applications[2:3],
            "query": "is:declined",
            "terms": ["is:declined"],
        }

    def test_is_submitted_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        organization_applications[0].status = OrganizationApplicationStatus.Approved
        organization_applications[1].status = OrganizationApplicationStatus.Approved
        organization_applications[2].status = OrganizationApplicationStatus.Declined
        organization_applications[3].status = OrganizationApplicationStatus.Submitted
        organization_applications[4].status = OrganizationApplicationStatus.Submitted
        db_request.GET["q"] = "is:submitted"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": organization_applications[3:],
            "query": "is:submitted",
            "terms": ["is:submitted"],
        }

    def test_type_query(self, db_request):
        company_org = OrganizationApplicationFactory.create(
            orgtype=OrganizationType.Company
        )
        community_org = OrganizationApplicationFactory.create(
            orgtype=OrganizationType.Community
        )
        db_request.GET["q"] = "type:company"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": [company_org],
            "query": "type:company",
            "terms": ["type:company"],
        }

        db_request.GET["q"] = "type:community"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": [community_org],
            "query": "type:community",
            "terms": ["type:community"],
        }

    def test_invalid_type_query(self, db_request):
        company_org = OrganizationApplicationFactory.create(
            orgtype=OrganizationType.Company
        )

        db_request.GET["q"] = "type:invalid"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": [company_org],
            "query": "type:invalid",
            "terms": ["type:invalid"],
        }

    def test_is_invalid_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(5),
            key=lambda o: o.submitted,
        )
        db_request.GET["q"] = "is:not-actually-a-valid-query"
        result = views.organization_applications_list(db_request)

        result.pop("check_summaries")
        assert result == {
            "organization_applications": organization_applications,
            "query": "is:not-actually-a-valid-query",
            "terms": ["is:not-actually-a-valid-query"],
        }

    def test_check_summaries(self, db_request):
        application = OrganizationApplicationFactory.create()
        rival = OrganizationApplicationFactory.create(
            name=application.name, status=OrganizationApplicationStatus.Deferred
        )
        decided = OrganizationApplicationFactory.create(
            name=application.name, status=OrganizationApplicationStatus.Approved
        )
        RoleFactory.create(user=application.submitted_by)

        summaries = views.organization_applications_list(db_request)["check_summaries"]

        assert decided.id not in summaries
        assert summaries[application.id][CheckStatus.Fail] == [
            "Applicant's primary email is verified"
        ]
        warnings = {
            open_application: summaries[open_application.id][CheckStatus.Warn]
            for open_application in (application, rival)
        }
        assert "No competing applications" in warnings[application]
        assert "No competing applications" in warnings[rival]
        assert "Applicant has projects" not in warnings[application]
        assert "Applicant has projects" in warnings[rival]


class TestOrganizationApplicationDetail:
    @pytest.fixture(autouse=True)
    def _csp(self, pyramid_services):
        pyramid_services.register_service(
            SimpleNamespace(merge=lambda policy: None), None, None, name="csp"
        )

    def test_detail(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["user"] == organization_application.submitted_by
        assert result["form"].name.data == organization_application.name
        assert result["conflicting_applications"] == []
        assert result["organization_application"] == organization_application
        assert result["applicant_reachable"] is False
        assert result["orphaned_name"] is False

    def test_detail_orphaned_name(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        OrganizationNameCatalogFactory.create(
            normalized_name=organization_application.normalized_name,
            organization_id=None,
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["orphaned_name"] is True

    def test_detail_reachable_applicant(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        EmailFactory.create(user=organization_application.submitted_by)
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["applicant_reachable"] is True

    def test_detail_edit(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )

        new_org_name = f"New-Org-Name-{organization_application.name}"
        db_request.method = "POST"
        db_request.POST["name"] = new_org_name
        db_request.POST["description"] = organization_application.description
        db_request.POST["display_name"] = organization_application.display_name
        db_request.POST["link_url"] = organization_application.link_url
        db_request.POST["orgtype"] = organization_application.orgtype
        db_request.POST = MultiDict(db_request.POST)

        db_request.current_route_path = lambda *a, **kw: "/the/url/"

        result = views.organization_application_detail(db_request)

        assert result.status_code == 303
        assert result.location == "/the/url/"
        assert db_request.session.pop_flash("success") == [
            f"Application for {organization_application.name!r} updated"
        ]

        assert organization_application.name == new_org_name

    def test_detail_edit_invalid(self, db_request):
        existing_organization = OrganizationFactory.create()
        organization_application = OrganizationApplicationFactory.create()

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.method = "POST"
        db_request.POST["name"] = existing_organization.name
        db_request.POST = MultiDict(db_request.POST)

        result = views.organization_application_detail(db_request)

        assert result["user"] == organization_application.submitted_by
        assert result["form"].name.data == existing_organization.name
        assert result["form"].name.errors != []
        assert result["conflicting_applications"] == []
        assert result["organization_application"] == organization_application

    def test_detail_edit_keeps_own_name(self, db_request):
        # The applicant's other open application, and the application itself,
        # only conflict on a rename.
        applicant = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            submitted_by=applicant,
            orgtype=OrganizationType.Company,
            status=OrganizationApplicationStatus.MoreInformationNeeded,
        )
        OrganizationApplicationFactory.create(
            submitted_by=applicant, name=organization_application.name
        )
        db_request.user = applicant
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "name": organization_application.name,
                "description": organization_application.description,
                "display_name": organization_application.display_name,
                "link_url": organization_application.link_url,
                "orgtype": "Community",
            }
        )
        db_request.current_route_path = lambda *a, **kw: "/the/url/"

        result = views.organization_application_detail(db_request)

        assert result.status_code == 303
        assert organization_application.orgtype == OrganizationType.Community

    def test_detail_edit_checks_applicants_applications(self, db_request):
        applicant = UserFactory.create()
        reviewer = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            submitted_by=applicant
        )
        OrganizationApplicationFactory.create(submitted_by=applicant, name="taken")
        OrganizationApplicationFactory.create(submitted_by=reviewer, name="free")
        db_request.user = reviewer
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.method = "POST"
        fields = {
            "description": organization_application.description,
            "display_name": organization_application.display_name,
            "link_url": organization_application.link_url,
            "orgtype": organization_application.orgtype.value,
        }
        db_request.current_route_path = lambda *a, **kw: "/the/url/"

        db_request.POST = MultiDict({"name": "taken", **fields})
        result = views.organization_application_detail(db_request)
        assert result["form"].name.errors == [
            "The applicant already has an open application for that name."
        ]

        db_request.POST = MultiDict({"name": "free", **fields})
        result = views.organization_application_detail(db_request)
        assert result.status_code == 303
        assert organization_application.name == "free"

    def test_detail_edit_name_taken_by_organization(self, db_request):
        # Another application for the name was approved while this one waited
        organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Deferred
        )
        OrganizationFactory.create(name=organization_application.name)
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "name": organization_application.name,
                "description": "Typo fixed",
                "display_name": organization_application.display_name,
                "link_url": organization_application.link_url,
                "orgtype": organization_application.orgtype.value,
            }
        )

        result = views.organization_application_detail(db_request)

        assert result["form"].name.errors == ["An organization already has that name."]
        assert organization_application.description != "Typo fixed"

    def test_detail_is_approved_true(self, db_request):
        organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Approved
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["user"] == organization_application.submitted_by
        assert result["form"].name.data == organization_application.name
        assert result["conflicting_applications"] == []
        assert result["organization_application"] == organization_application

    def test_detail_is_approved_false(self, db_request):
        organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Declined
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["user"] == organization_application.submitted_by
        assert result["form"].name.data == organization_application.name
        assert result["conflicting_applications"] == []
        assert result["organization_application"] == organization_application

    @pytest.mark.parametrize(
        ("name", "conflicts", "conflicting_prefixes", "not_conflicting"),
        [
            (
                "pypi",
                ["PyPI", "pypi"],
                ["pypi-common", "PyPi_rocks", "pypi-team-garbage"],
                ["py-pi"],
            ),
            ("py-pi", ["Py-PI", "PY-PI"], ["py", "py-pi_dot-com"], ["pypi"]),
        ],
    )
    def test_detail_conflicting_applications(
        self, db_request, name, conflicts, conflicting_prefixes, not_conflicting
    ):
        organization_application = OrganizationApplicationFactory.create(
            name=name, status=OrganizationApplicationStatus.Declined
        )
        conflicting_applications = sorted(
            [
                OrganizationApplicationFactory.create(name=conflict)
                for conflict in conflicts + conflicting_prefixes
            ],
            key=lambda o: o.submitted,
        )
        [OrganizationApplicationFactory.create(name=name) for name in not_conflicting]
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        result = views.organization_application_detail(db_request)
        assert result["user"] == organization_application.submitted_by
        assert result["form"].name.data == organization_application.name
        assert set(result["conflicting_applications"]) == set(conflicting_applications)
        assert result["organization_application"] == organization_application

    def test_detail_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_detail(db_request)

    def test_detail_queue(self, db_request):
        def submitted_at(day, **kw):
            return OrganizationApplicationFactory.create(
                submitted=dt.datetime(2024, 1, day), **kw
            )

        oldest, middle, newest = submitted_at(1), submitted_at(2), submitted_at(4)
        deferred = submitted_at(3, status=OrganizationApplicationStatus.Deferred)

        def queue_for(application):
            db_request.matchdict["organization_application_id"] = application.id
            return views.organization_application_detail(db_request)["queue"]

        assert queue_for(middle) == {
            "total": 3,
            "position": 2,
            "previous": oldest,
            "next": newest,
        }
        # The next application wraps around to the oldest; the previous does not.
        assert queue_for(newest)["next"] == oldest
        assert queue_for(oldest)["previous"] is None
        # An application outside the queue still knows its neighbours, by date.
        assert queue_for(deferred) == {
            "total": 3,
            "position": None,
            "previous": middle,
            "next": newest,
        }


class TestOrganizationApplicationActions:
    def test_approve(self, db_request, mocker):
        send_approved = mocker.patch.object(
            services, "send_new_organization_approved_email"
        )
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_name"] = organization_application.name
        db_request.params["message"] = "Welcome!"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_approve(db_request)

        organization = organization_application.organization
        assert organization is not None
        assert organization_application.status == OrganizationApplicationStatus.Approved
        send_approved.assert_called_once_with(
            db_request,
            user,
            organization_name=organization.name,
            organization_type=organization.orgtype,
            message="Welcome!",
        )
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization.name}" organization approved'
        ]
        assert result.status_code == 303
        assert result.location == f"/admin/organizations/{organization.id}/"

    def test_approve_reserved_name(self, db_request, mocker):
        send_approved = mocker.patch.object(
            services, "send_new_organization_approved_email"
        )
        organization_application = OrganizationApplicationFactory.create(name="example")
        OrganizationNameCatalogFactory.create(
            normalized_name="example", organization_id=None
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_application_approve(db_request)

        assert organization_application.status == (
            OrganizationApplicationStatus.Submitted
        )
        assert organization_application.organization is None
        send_approved.assert_not_called()
        assert db_request.session.pop_flash("error") == [
            'The name "example" is already reserved'
        ]
        assert result.location == (
            f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_approve_turbo_mode(self, db_request, mocker):
        mocker.patch.object(services, "send_new_organization_approved_email")
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_name"] = organization_application.name
        db_request.params["message"] = "Welcome!"
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_approve(db_request)

        organization = organization_application.organization
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization.name}" organization approved',
            "No more Organization Applications to review!",
        ]
        assert result.status_code == 303
        assert result.location == "/admin/"

    def test_approve_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_approve(db_request)

    def test_defer(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_defer(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Deferred
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization_application.name}" organization deferred'
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_defer_with_note(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = admin
        db_request.route_path = _organization_application_routes
        db_request.params["message"] = "Jurisdiction review pending."

        result = views.organization_application_defer(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Deferred
        assert [note.payload["message"] for note in organization_application.notes] == [
            "Jurisdiction review pending."
        ]
        assert result.status_code == 303

    def test_defer_turbo_mode(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_defer(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Deferred
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization_application.name}" organization deferred',
            "No more Organization Applications to review!",
        ]
        assert result.status_code == 303
        assert result.location == "/admin/"

    def test_defer_turbo_mode_with_next_application(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )
        next_application = OrganizationApplicationFactory.create(name="next")

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_defer(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Deferred
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{next_application.id}/"
        )

    def test_defer_turbo_mode_moves_to_following_application(self, db_request):
        _oldest, current, newer = (
            OrganizationApplicationFactory.create(submitted=dt.datetime(2024, 1, day))
            for day in (1, 2, 3)
        )
        db_request.matchdict["organization_application_id"] = current.id
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_application_defer(db_request)

        # Not back to the oldest: the reviewer carries on down the queue.
        assert result.location == f"/admin/organization_applications/{newer.id}/"

    def test_defer_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_defer(db_request)

    def test_request_more_information(self, db_request, mocker):
        send_email = mocker.patch.object(
            services, "send_new_organization_moreinformationneeded_email"
        )
        admin = UserFactory.create()
        user = UserFactory.create()
        EmailFactory.create(user=user)
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Welcome!"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_request_more_information(db_request)

        assert (
            organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert len(organization_application.observations) == 1
        send_email.assert_called_once_with(
            db_request,
            user,
            organization_name=organization_application.name,
            organization_application_id=organization_application.id,
            message="Welcome!",
        )
        assert db_request.session.pop_flash("success") == [
            (
                f'Request for more info from "{organization_application.name}" '
                "organization sent"
            )
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_request_more_information_turbo_mode(self, db_request, mocker):
        mocker.patch.object(
            services, "send_new_organization_moreinformationneeded_email"
        )
        admin = UserFactory.create()
        user = UserFactory.create()
        EmailFactory.create(user=user)
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Welcome!"
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_request_more_information(db_request)

        assert (
            organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert db_request.session.pop_flash("success") == [
            (
                f'Request for more info from "{organization_application.name}" '
                "organization sent"
            ),
            "No more Organization Applications to review!",
        ]
        assert result.status_code == 303
        assert result.location == "/admin/"

    def test_request_more_information_for_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_request_more_information(db_request)

    def test_request_more_information_no_message(self, db_request, mocker):
        send_email = mocker.patch.object(
            services, "send_new_organization_moreinformationneeded_email"
        )
        admin = UserFactory.create()
        user = UserFactory.create()
        EmailFactory.create(user=user)
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_request_more_information(db_request)

        assert len(organization_application.observations) == 0
        send_email.assert_not_called()
        assert db_request.session.pop_flash("error") == ["No message provided"]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.parametrize(
        "email_kwargs", [None, {"verified": False}, {"primary": False}]
    )
    def test_request_more_information_unreachable_applicant(
        self, db_request, mocker, email_kwargs
    ):
        send_email = mocker.patch.object(
            services, "send_new_organization_moreinformationneeded_email"
        )
        user = UserFactory.create()
        if email_kwargs is not None:
            EmailFactory.create(user=user, **email_kwargs)
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Welcome!"
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_application_request_more_information(db_request)

        assert (
            organization_application.status == OrganizationApplicationStatus.Submitted
        )
        assert len(organization_application.observations) == 0
        send_email.assert_not_called()
        assert db_request.session.pop_flash("error") == [
            (
                'Cannot request more info for "example": '
                "the applicant has no verified primary email"
            )
        ]
        assert db_request.session.pop_flash("success") == []
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_decline(self, db_request, mocker):
        send_email = mocker.patch.object(
            services, "send_new_organization_declined_email"
        )
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_name"] = organization_application.name
        db_request.params["message"] = "Sorry!"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_decline(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Declined
        send_email.assert_called_once_with(
            db_request,
            user,
            organization_name=organization_application.name,
            message="Sorry!",
        )
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization_application.name}" organization declined'
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_decline_turbo_mode(self, db_request, mocker):
        mocker.patch.object(services, "send_new_organization_declined_email")
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["organization_name"] = organization_application.name
        db_request.params["message"] = "Sorry!"
        db_request.params["organization_applications_turbo_mode"] = "true"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_decline(db_request)

        assert organization_application.status == OrganizationApplicationStatus.Declined
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization_application.name}" organization declined',
            "No more Organization Applications to review!",
        ]
        assert result.status_code == 303
        assert result.location == "/admin/"

    def test_decline_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_decline(db_request)

    @pytest.mark.parametrize(
        "view",
        [
            views.organization_application_approve,
            views.organization_application_defer,
            views.organization_application_request_more_information,
            views.organization_application_decline,
        ],
    )
    def test_action_on_withdrawn(self, db_request, view):
        db_request.user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", status=OrganizationApplicationStatus.Submitted
        )
        # The applicant withdraws after this request loaded the application.
        db_request.db.execute(
            update(OrganizationApplication)
            .where(OrganizationApplication.id == organization_application.id)
            .values(status=OrganizationApplicationStatus.Withdrawn)
            .execution_options(synchronize_session=False)
        )
        assert (
            organization_application.status == OrganizationApplicationStatus.Submitted
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Sorry!"
        db_request.route_path = _organization_application_routes

        with pytest.raises(HTTPSeeOther) as redirect:
            view(db_request)

        assert (
            organization_application.status == OrganizationApplicationStatus.Withdrawn
        )
        assert organization_application.organization is None
        assert db_request.session.pop_flash("error") == [
            '"example" is already withdrawn'
        ]
        assert redirect.value.location == (
            f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_addnote(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Some internal note"
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_add_note(db_request)

        assert len(organization_application.observations) == 1
        assert organization_application.observations[0].payload == {
            "message": "Some internal note"
        }
        assert db_request.session.pop_flash("success") == [
            f'Note added to "{organization_application.name}" application'
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_addnote_no_message(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = admin
        db_request.route_path = _organization_application_routes

        result = views.organization_application_add_note(db_request)

        assert len(organization_application.observations) == 0
        assert db_request.session.pop_flash("error") == ["No note text provided"]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_addnote_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_add_note(db_request)

    def test_release_name(self, db_request):
        organization_application = OrganizationApplicationFactory.create(name="example")
        OrganizationNameCatalogFactory.create(
            normalized_name="example", organization_id=None
        )
        other = OrganizationNameCatalogFactory.create(
            normalized_name="other", organization_id=None
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_application_release_name(db_request)

        assert db_request.db.query(OrganizationNameCatalog).all() == [other]
        assert [o.payload for o in organization_application.observations] == [
            {"message": "Released the name 'example' from a deleted organization."}
        ]
        assert db_request.session.pop_flash("success") == [
            'Released the name "example"'
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    def test_release_name_keeps_live_organization(self, db_request):
        organization_application = OrganizationApplicationFactory.create(name="example")
        organization = OrganizationFactory.create(name="example")
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_application_release_name(db_request)

        assert [
            entry.organization_id
            for entry in db_request.db.query(OrganizationNameCatalog).all()
        ] == [organization.id]
        assert organization_application.observations == []
        assert db_request.session.pop_flash("error") == [
            'The name "example" is not held by a deleted organization'
        ]
        assert result.status_code == 303

    def test_release_name_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_release_name(db_request)

    def test_request_more_information_preview_not_found(self, db_request):
        db_request.matchdict["organization_application_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.organization_application_request_more_information_preview(db_request)

    @pytest.mark.parametrize(
        "status",
        [
            OrganizationApplicationStatus.Approved,
            OrganizationApplicationStatus.Declined,
        ],
    )
    @pytest.mark.parametrize(
        "view",
        [
            views.organization_application_approve,
            views.organization_application_defer,
            views.organization_application_request_more_information,
            views.organization_application_decline,
        ],
    )
    def test_decided_application_keeps_its_decision(
        self, db_request, mocker, status, view
    ):
        emails = [
            mocker.patch.object(services, f"send_new_organization_{name}_email")
            for name in ("approved", "declined", "moreinformationneeded")
        ]
        organization_application = OrganizationApplicationFactory.create(
            name="example", status=status
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        db_request.params["message"] = "Stale page"
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        with pytest.raises(HTTPSeeOther) as redirect:
            view(db_request)

        assert redirect.value.location == (
            f"/admin/organization_applications/{organization_application.id}/"
        )
        assert db_request.session.pop_flash("error") == [
            f'"example" is already {status.value}'
        ]
        assert organization_application.status == status
        assert organization_application.organization is None
        assert organization_application.observations == []
        for email in emails:
            email.assert_not_called()


class TestOrganizationNames:
    def test_list(self, db_request):
        beta = OrganizationNameCatalogFactory.create(
            normalized_name="beta", organization_id=None
        )
        alpha = OrganizationNameCatalogFactory.create(
            normalized_name="alpha", organization_id=None
        )
        OrganizationFactory.create(name="gamma")
        open_application = OrganizationApplicationFactory.create(name="Alpha")
        OrganizationApplicationFactory.create(
            name="alpha", status=OrganizationApplicationStatus.Declined
        )

        result = views.organization_name_list(db_request)

        assert list(result["names"]) == [alpha, beta]
        assert result["open_applications"] == {"alpha": [open_application]}
        assert result["query"] == ""

    def test_list_query(self, db_request):
        match = OrganizationNameCatalogFactory.create(
            normalized_name="acme-labs", organization_id=None
        )
        OrganizationNameCatalogFactory.create(
            normalized_name="other", organization_id=None
        )
        db_request.params["q"] = "ACME_Labs"

        result = views.organization_name_list(db_request)

        assert list(result["names"]) == [match]

    def test_list_invalid_page(self, db_request):
        db_request.params["page"] = "not an integer"

        with pytest.raises(HTTPBadRequest):
            views.organization_name_list(db_request)

    def test_release(self, db_request):
        OrganizationNameCatalogFactory.create(
            normalized_name="alpha", organization_id=None
        )
        other = OrganizationNameCatalogFactory.create(
            normalized_name="beta", organization_id=None
        )
        open_application = OrganizationApplicationFactory.create(name="alpha")
        declined = OrganizationApplicationFactory.create(
            name="alpha", status=OrganizationApplicationStatus.Declined
        )
        db_request.POST["normalized_name"] = "alpha"
        db_request.user = UserFactory.create()
        db_request.route_path = _organization_application_routes

        result = views.organization_name_release(db_request)

        assert db_request.db.query(OrganizationNameCatalog).all() == [other]
        assert [o.payload for o in open_application.observations] == [
            {"message": "Released the name 'alpha' from a deleted organization."}
        ]
        assert declined.observations == []
        assert db_request.session.pop_flash("success") == ['Released the name "alpha"']
        assert result.status_code == 303
        assert result.location == "/admin/organization_names/"

    def test_release_keeps_live_organization(self, db_request):
        organization = OrganizationFactory.create(name="alpha")
        db_request.POST["normalized_name"] = "alpha"
        db_request.route_path = _organization_application_routes

        result = views.organization_name_release(db_request)

        assert [
            entry.organization_id
            for entry in db_request.db.query(OrganizationNameCatalog).all()
        ] == [organization.id]
        assert db_request.session.pop_flash("error") == [
            'The name "alpha" is not held by a deleted organization'
        ]
        assert result.location == "/admin/organization_names/"
