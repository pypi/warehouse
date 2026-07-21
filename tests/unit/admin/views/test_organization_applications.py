# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest

from pyramid.httpexceptions import HTTPNotFound
from webob.multidict import MultiDict

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
)
from warehouse.admin.views import organizations as views
from warehouse.organizations import services
from warehouse.organizations.models import (
    OrganizationApplicationStatus,
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
    pytest.fail(f"No dummy route found for {route_name}")


class TestOrganizationApplicationList:
    def test_no_query(self, db_request):
        organization_applications = sorted(
            OrganizationApplicationFactory.create_batch(30),
            key=lambda o: o.submitted,
        )
        result = views.organization_applications_list(db_request)

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

        assert result == {
            "organization_applications": [company_org],
            "query": "type:company",
            "terms": ["type:company"],
        }

        db_request.GET["q"] = "type:community"
        result = views.organization_applications_list(db_request)

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

        assert result == {
            "organization_applications": organization_applications,
            "query": "is:not-actually-a-valid-query",
            "terms": ["is:not-actually-a-valid-query"],
        }


class TestOrganizationApplicationDetail:
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
            message="Welcome!",
        )
        assert db_request.session.pop_flash("success") == [
            f'Request for "{organization.name}" organization approved'
        ]
        assert result.status_code == 303
        assert result.location == f"/admin/organizations/{organization.id}/"

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
