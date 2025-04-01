# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.accounts.interfaces import IUserService
from warehouse.admin.views import organizations as views
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationApplicationStatus,
    OrganizationType,
)

from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
)


class TestOrganizationList:

    @pytest.mark.usefixtures("_enable_organizations")
    def test_no_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(30),
            key=lambda o: o.normalized_name,
        )
        result = views.organization_list(db_request)

        assert result == {"organizations": organizations[:25], "query": "", "terms": []}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_with_page(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(30),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["page"] = "2"
        result = views.organization_list(db_request)

        assert result == {"organizations": organizations[25:], "query": "", "terms": []}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_with_invalid_page(self):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            params={"page": "not an integer"},
        )

        with pytest.raises(HTTPBadRequest):
            views.organization_list(request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_basic_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = organizations[0].name
        result = views.organization_list(db_request)

        assert organizations[0] in result["organizations"]
        assert result["query"] == organizations[0].name
        assert result["terms"] == [organizations[0].name]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_name_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"name:{organizations[0].name}"
        result = views.organization_list(db_request)

        assert organizations[0] in result["organizations"]
        assert result["query"] == f"name:{organizations[0].name}"
        assert result["terms"] == [f"name:{organizations[0].name}"]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_organization_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"organization:{organizations[0].display_name}"
        result = views.organization_list(db_request)

        assert organizations[0] in result["organizations"]
        assert result["query"] == f"organization:{organizations[0].display_name}"
        assert result["terms"] == [f"organization:{organizations[0].display_name}"]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_url_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"url:{organizations[0].link_url}"
        result = views.organization_list(db_request)

        assert organizations[0] in result["organizations"]
        assert result["query"] == f"url:{organizations[0].link_url}"
        assert result["terms"] == [f"url:{organizations[0].link_url}"]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_description_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"description:'{organizations[0].description}'"
        result = views.organization_list(db_request)

        assert organizations[0] in result["organizations"]
        assert result["query"] == f"description:'{organizations[0].description}'"
        assert result["terms"] == [f"description:{organizations[0].description}"]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_is_active_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_active = True
        organizations[1].is_active = True
        organizations[2].is_active = False
        organizations[3].is_active = False
        organizations[4].is_active = False
        db_request.GET["q"] = "is:active"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[:2],
            "query": "is:active",
            "terms": ["is:active"],
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_is_inactive_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_active = True
        organizations[1].is_active = True
        organizations[2].is_active = False
        organizations[3].is_active = False
        organizations[4].is_active = False
        db_request.GET["q"] = "is:inactive"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[2:],
            "query": "is:inactive",
            "terms": ["is:inactive"],
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_type_query(self, db_request):
        company_org = OrganizationFactory.create(orgtype=OrganizationType.Company)
        community_org = OrganizationFactory.create(orgtype=OrganizationType.Community)
        db_request.GET["q"] = "type:company"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [company_org],
            "query": "type:company",
            "terms": ["type:company"],
        }

        db_request.GET["q"] = "type:community"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [community_org],
            "query": "type:community",
            "terms": ["type:community"],
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_invalid_type_query(self, db_request):
        company_org = OrganizationFactory.create(orgtype=OrganizationType.Company)

        db_request.GET["q"] = "type:invalid"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [company_org],
            "query": "type:invalid",
            "terms": ["type:invalid"],
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_is_invalid_query(self, db_request):
        organizations = sorted(
            OrganizationFactory.create_batch(5),
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = "is:not-actually-a-valid-query"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[:25],
            "query": "is:not-actually-a-valid-query",
            "terms": ["is:not-actually-a-valid-query"],
        }


class TestOrganizationDetail:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail(self):
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            status=OrganizationApplicationStatus.Submitted,
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "organization": organization,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_true(self):
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=True,
            status=OrganizationApplicationStatus.Approved,
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "organization": organization,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_false(self):
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            status=OrganizationApplicationStatus.Declined,
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "organization": organization,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_not_found(self):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_detail(request)


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
        assert views.organization_application_detail(db_request) == {
            "user": organization_application.submitted_by,
            "conflicting_applications": [],
            "organization_application": organization_application,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_true(self, db_request):
        organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Approved
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        assert views.organization_application_detail(db_request) == {
            "user": organization_application.submitted_by,
            "conflicting_applications": [],
            "organization_application": organization_application,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_false(self, db_request):
        organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Declined
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        assert views.organization_application_detail(db_request) == {
            "user": organization_application.submitted_by,
            "conflicting_applications": [],
            "organization_application": organization_application,
        }

    @pytest.mark.usefixtures("_enable_organizations")
    @pytest.mark.parametrize(
        ("name", "conflicts"),
        [
            ("pypi", ["PyPI", "pypi"]),
            ("py-pi", ["Py-PI", "PY-PI"]),
        ],
    )
    def test_detail_conflicting_applications(self, db_request, name, conflicts):
        organization_application = OrganizationApplicationFactory.create(
            name=name, status=OrganizationApplicationStatus.Declined
        )
        conflicting_applications = sorted(
            [
                OrganizationApplicationFactory.create(name=conflict)
                for conflict in conflicts
            ],
            key=lambda o: o.submitted,
        )
        db_request.matchdict["organization_application_id"] = (
            organization_application.id
        )
        assert views.organization_application_detail(db_request) == {
            "user": organization_application.submitted_by,
            "conflicting_applications": conflicting_applications,
            "organization_application": organization_application,
        }

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


class TestActions:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve(self, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admin_user=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        organization = pretend.stub(
            id="fizzbuzz", name="example", record_event=lambda *a, **kw: None
        )
        organization_application = pretend.stub(
            id="wizzbang", name="example", submitted_by=user, submitted_by_id=user.id
        )
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            approve_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization
            ),
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        message = pretend.stub()
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={"organization_name": organization.name, "message": message},
            route_path=lambda *a, **kw: organization_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
            user=admin,
        )

        result = views.organization_application_approve(request)

        assert organization_service.approve_organization_application.calls == [
            pretend.call(organization_application.id, request),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization.name}" organization approved',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization_application = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_application_approve(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

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
    def test_defer(self, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admin_user=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )

        organization_application = pretend.stub(
            id="wizzbang", name="example", submitted_by=user, submitted_by_id=user.id
        )
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            defer_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={
                "organization_name": organization_application.name,
            },
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
            user=admin,
        )

        result = views.organization_application_defer(request)

        assert organization_service.defer_organization_application.calls == [
            pretend.call(organization_application.id, request),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization deferred',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

    @pytest.mark.usefixtures("_enable_organizations")
    def test_defer_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization_application = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_application_defer(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

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
    def test_request_more_information(self, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admin_user=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )

        organization_application = pretend.stub(
            id="wizzbang", name="example", submitted_by=user, submitted_by_id=user.id
        )
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            request_more_information=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        message = pretend.stub()
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={
                "organization_name": organization_application.name,
                "message": message,
            },
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
            user=admin,
        )

        result = views.organization_application_request_more_information(request)

        assert organization_service.request_more_information.calls == [
            pretend.call(organization_application.id, request),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                (
                    f'Request for more info from "{organization_application.name}" '
                    "organization sent"
                ),
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information_for_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization_application = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_application_request_more_information(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

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
    def test_decline(self, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admin_user=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )

        organization_application = pretend.stub(
            id="wizzbang", name="example", submitted_by=user, submitted_by_id=user.id
        )
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
            decline_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization_application
            ),
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        message = pretend.stub()
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={
                "organization_name": organization_application.name,
                "message": message,
            },
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
            user=admin,
        )

        result = views.organization_application_decline(request)

        assert organization_service.decline_organization_application.calls == [
            pretend.call(organization_application.id, request),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization declined',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

    @pytest.mark.usefixtures("_enable_organizations")
    def test_decline_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization_application = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization_application=lambda *a, **kw: organization_application,
        )
        organization_application_detail_location = (
            f"/admin/organization_applications/{organization_application.id}/",
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_application_id": organization_application.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_application_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_application_decline(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_application_detail_location

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
