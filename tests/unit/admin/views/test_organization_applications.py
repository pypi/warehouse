# SPDX-License-Identifier: Apache-2.0
import pretend
import pytest

from pyramid.httpexceptions import HTTPNotFound
from webob.multidict import MultiDict

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
)
from warehouse.admin.views import organizations as views
from warehouse.organizations.models import (
    OrganizationApplicationStatus,
    OrganizationType,
)


def _organization_application_routes(
    route_name, organization_application_id=None, organization_id=None
):
    if route_name == "admin.organization_application.detail":
        return f"/admin/organization_applications/{organization_application_id}/"
    elif route_name == "admin.organization.detail":
        return f"/admin/organizations/{organization_id}/"
    elif route_name == "admin.dashboard":
        return "/admin/"
    else:
        pytest.fail(f"No dummy route found for {route_name}")


class TestOrganizationApplicationList:
    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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
    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.current_route_path = lambda *a, **kw: "/the/url/"

        result = views.organization_application_detail(db_request)

        assert result.status_code == 303
        assert result.location == "/the/url/"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Application for {organization_application.name!r} updated",
                queue="success",
            )
        ]

        assert organization_application.name == new_org_name

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
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

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_not_found(self):
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_application_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_application_detail(request)


class TestOrganizationApplicationActions:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )
        organization = OrganizationFactory.create(name="example")

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            approve_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {
            "organization_name": organization_application.name,
            "message": "Welcome!",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_approve(db_request)

        assert organization_service.approve_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization approved',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == f"/admin/organizations/{organization.id}/"

    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve_turbo_mode(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )
        organization = OrganizationFactory.create(name="example")

        def _approve(*a, **kw):
            db_request.db.delete(organization_application)
            return organization

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            approve_organization_application=pretend.call_recorder(_approve),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {
            "organization_name": organization_application.name,
            "message": "Welcome!",
            "organization_applications_turbo_mode": "true",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_approve(db_request)

        assert organization_service.approve_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization approved',
                queue="success",
            ),
            pretend.call(
                "No more Organization Applications to review!",
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == "/admin/"

    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve_not_found(self):
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_application_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_application_approve(request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_defer(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            defer_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {}
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_defer(db_request)

        assert organization_service.defer_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization deferred',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_defer_turbo_mode(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            defer_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {"organization_applications_turbo_mode": "true"}
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_defer(db_request)

        assert organization_service.defer_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization deferred',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_defer_not_found(self):
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_application_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_application_defer(request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            request_more_information=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {"message": "Welcome!"}
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_request_more_information(db_request)

        assert organization_service.request_more_information.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    f'Request for more info from "{organization_application.name}" '
                    "organization sent"
                ),
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information_turbo_mode(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            request_more_information=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {
            "message": "Welcome!",
            "organization_applications_turbo_mode": "true",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_request_more_information(db_request)

        assert organization_service.request_more_information.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    f'Request for more info from "{organization_application.name}" '
                    "organization sent"
                ),
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information_for_not_found(self):
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_application_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_application_request_more_information(request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information_no_message(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            request_more_information=pretend.call_recorder(pretend.raiser(ValueError)),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {}
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_request_more_information(db_request)

        assert organization_service.request_more_information.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call("No message provided", queue="error"),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_decline(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            decline_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {
            "organization_name": organization_application.name,
            "message": "Sorry!",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_decline(db_request)

        assert organization_service.decline_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization declined',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_decline_turbo_mode(self, db_request):
        admin = UserFactory.create()
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            name="example", submitted_by=user
        )

        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            decline_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )

        db_request.matchdict = {
            "organization_application_id": organization_application.id
        }
        db_request.params = {
            "organization_name": organization_application.name,
            "message": "Sorry!",
            "organization_applications_turbo_mode": "true",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: organization_service
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_application_decline(db_request)

        assert organization_service.decline_organization_application.calls == [
            pretend.call(organization_application.id, db_request),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization declined',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert (
            result.location
            == f"/admin/organization_applications/{organization_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_decline_not_found(self):
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_application_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_application_decline(request)
