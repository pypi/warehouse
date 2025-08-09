# SPDX-License-Identifier: Apache-2.0

import datetime

import freezegun
import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.response import Response
from sqlalchemy import and_
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.admin.views import organizations as views
from warehouse.constants import ONE_GIB, ONE_MIB
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.subscriptions.models import StripeCustomer

from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationRoleFactory,
)
from ....common.db.accounts import UserFactory
from ....common.db.subscriptions import StripeCustomerFactory


@pytest.fixture
def enable_organizations(request, db_request, monkeypatch):
    monkeypatch.setattr(db_request, "organization_access", True)


class TestOrganizationList:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_no_query(self, db_request):
        page = pretend.stub()
        organizations_query = pretend.stub()
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": "",
            "terms": [],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_with_page(self, db_request):
        page = pretend.stub()
        organizations_query = pretend.stub()
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["page"] = "2"

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": "",
            "terms": [],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_with_invalid_page(self, db_request):
        db_request.GET["page"] = "not integer"

        with pytest.raises(HTTPBadRequest):
            views.organization_list(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_basic_query(self, db_request):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = "foo"

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": "foo",
            "terms": ["foo"],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]
        assert organizations_query.filter.calls == [pretend.call(False)]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_wildcard_query(self, db_request):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = "foo%"

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": "foo%",
            "terms": ["foo%"],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]
        assert organizations_query.filter.calls == [pretend.call(False)]

    @pytest.mark.parametrize("field", ["name", "org", "organization", "url", "link_url", "desc", "description"])
    def test_field_query(self, db_request, field):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = f"{field}:foo"

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": f"{field}:foo",
            "terms": [f"{field}:foo"],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]

    @pytest.mark.parametrize("query", ["is:active", "is:inactive"])
    def test_is_query(self, db_request, query):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = query

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": query,
            "terms": [query],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]

    @pytest.mark.parametrize("query", ["type:company", "type:community"])
    def test_type_query(self, db_request, query):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = query

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": query,
            "terms": [query],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]

    def test_quoted_name_query(self, db_request):
        page = pretend.stub()
        organizations_query = pretend.stub(
            filter=pretend.call_recorder(lambda *a: organizations_query),
            options=pretend.call_recorder(lambda *a: organizations_query),
            order_by=pretend.call_recorder(lambda *a: organizations_query),
        )
        db_request.db.query = pretend.call_recorder(lambda *a: organizations_query)
        organization_query_paginate = pretend.call_recorder(lambda *a, **kw: page)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", organization_query_paginate)
        db_request.GET["q"] = 'name:"foo bar"'

        assert views.organization_list(db_request) == {
            "organizations": page,
            "query": 'name:"foo bar"',
            "terms": ["name:foo bar"],
        }
        assert db_request.db.query.calls == [pretend.call(Organization)]


class TestOrganizationDetail:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_not_found(self, db_request):
        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda *a: None)
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {"organization_id": "00000000-0000-0000-0000-000000000000"}

        with pytest.raises(HTTPNotFound):
            views.organization_detail(db_request)

        assert organization_service.get_organization.calls == [
            pretend.call("00000000-0000-0000-0000-000000000000")
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_post_update_billing_name(self, db_request, monkeypatch):
        billing_service = pretend.stub(
            update_customer=pretend.call_recorder(lambda *a: None)
        )
        customer = StripeCustomerFactory.create()
        organization = OrganizationFactory.create(
            customer=customer,
            name="example",
            display_name="Example",
            orgtype=OrganizationType.Company,
            link_url="https://www.example.com/",
            description="An example organization for testing",
            is_active=False,
        )
        monkeypatch.setattr(
            organization,
            "customer_name",
            lambda site_name: f"{organization.name} (via {site_name})",
        )
        db_request.registry.settings = {"site.name": "PyPI"}
        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda *a: organization)
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: {
                views.IOrganizationService: organization_service,
                views.IBillingService: billing_service,
            }[service]
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "POST"
        db_request.POST = {
            "display_name": "New Example",
            "link_url": "https://www.new-example.com/",
            "description": "A new example organization for testing",
            "orgtype": str(OrganizationType.Company.value),
        }
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_detail(db_request)

        assert billing_service.update_customer.calls == [
            pretend.call(
                customer.customer_id,
                "example (via PyPI)",
                "A new example organization for testing",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/foo/bar/"
        assert organization.display_name == "New Example"
        assert organization.link_url == "https://www.new-example.com/"
        assert organization.description == "A new example organization for testing"
        assert organization.orgtype == OrganizationType.Company
        assert db_request.session.flash.calls == [
            pretend.call("Organization 'example' updated successfully", queue="success")
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_false(self, db_request):
        organization = OrganizationFactory.create(
            name="example",
            display_name="Example",
            orgtype=OrganizationType.Company,
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)
        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        assert result["ONE_MIB"] == views.ONE_MIB
        assert result["MAX_FILESIZE"] == views.MAX_FILESIZE
        assert result["ONE_GIB"] == views.ONE_GIB
        assert result["MAX_PROJECT_SIZE"] == views.MAX_PROJECT_SIZE
        assert result["UPLOAD_LIMIT_CAP"] == views.UPLOAD_LIMIT_CAP
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_is_approved_true(self, db_request):
        organization = OrganizationFactory.create(
            name="example",
            display_name="Example",
            orgtype=OrganizationType.Company,
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=True,
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)
        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        assert result["ONE_MIB"] == views.ONE_MIB
        assert result["MAX_FILESIZE"] == views.MAX_FILESIZE
        assert result["ONE_GIB"] == views.ONE_GIB
        assert result["MAX_PROJECT_SIZE"] == views.MAX_PROJECT_SIZE
        assert result["UPLOAD_LIMIT_CAP"] == views.UPLOAD_LIMIT_CAP
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_with_subscription(self, db_request, monkeypatch):
        customer = StripeCustomerFactory.create()
        organization = OrganizationFactory.create(
            customer=customer,
            name="example",
            display_name="Example",
            orgtype=OrganizationType.Company,
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=True,
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)
        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        assert result["ONE_MIB"] == views.ONE_MIB
        assert result["MAX_FILESIZE"] == views.MAX_FILESIZE
        assert result["ONE_GIB"] == views.ONE_GIB
        assert result["MAX_PROJECT_SIZE"] == views.MAX_PROJECT_SIZE
        assert result["UPLOAD_LIMIT_CAP"] == views.UPLOAD_LIMIT_CAP
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_with_roles(self, db_request):
        organization = OrganizationFactory.create(name="example", is_active=True)
        user1 = UserFactory.create(username="alice")
        user2 = UserFactory.create(username="bob")
        role1 = OrganizationRoleFactory.create(
            organization=organization,
            user=user1,
            role_name=OrganizationRoleType.Manager,
        )
        role2 = OrganizationRoleFactory.create(
            organization=organization,
            user=user2,
            role_name=OrganizationRoleType.Member,
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)
        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        # Roles should be sorted by username
        assert result["roles"] == [role1, role2]  # alice before bob
        assert len(result["role_forms"]) == 2
        assert role1.id in result["role_forms"]
        assert role2.id in result["role_forms"]
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)


class TestOrganizationRename:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_not_found(self, db_request):
        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda *a: None)
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {"organization_id": "00000000-0000-0000-0000-000000000000"}

        with pytest.raises(HTTPNotFound):
            views.organization_rename(db_request)

        assert organization_service.get_organization.calls == [
            pretend.call("00000000-0000-0000-0000-000000000000")
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename_success(self, db_request):
        organization = OrganizationFactory.create(name="oldname")
        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda *a: organization),
            rename_organization=pretend.call_recorder(lambda *a: None),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.params = {"new_organization_name": "newname"}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_rename(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/1/"
        assert organization_service.rename_organization.calls == [
            pretend.call(str(organization.id), "newname")
        ]
        assert db_request.session.flash.calls == [
            pretend.call('"oldname" organization renamed "newname"', queue="success")
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename_validation_error(self, db_request):
        organization = OrganizationFactory.create(name="oldname")
        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda *a: organization),
            rename_organization=pretend.raiser(
                ValueError("Organization name already exists")
            ),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.params = {"new_organization_name": "existing"}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_rename(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/1/"
        assert db_request.session.flash.calls == [
            pretend.call("Organization name already exists", queue="error")
        ]


class TestOrganizationApplicationsList:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_no_query(self, db_request):
        organization_applications = [
            OrganizationApplicationFactory.create(),
            OrganizationApplicationFactory.create(),
        ]
        db_request.GET = {"q": ""}

        result = views.organization_applications_list(db_request)

        assert result == {
            "organization_applications": organization_applications,
            "query": "",
            "terms": [],
        }

    @pytest.mark.usefixtures("_enable_organizations")
    def test_with_query(self, db_request):
        org1 = OrganizationApplicationFactory.create(name="foo")
        OrganizationApplicationFactory.create(name="bar")
        db_request.GET = {"q": "foo"}

        result = views.organization_applications_list(db_request)

        assert result == {
            "organization_applications": [org1],
            "query": "foo",
            "terms": ["foo"],
        }

    @pytest.mark.parametrize("field", ["name", "org", "organization", "url", "link_url", "desc", "description"])
    def test_field_query(self, db_request, field):
        org1 = OrganizationApplicationFactory.create()
        db_request.GET = {"q": f"{field}:test"}

        result = views.organization_applications_list(db_request)

        assert result["query"] == f"{field}:test"
        assert result["terms"] == [f"{field}:test"]

    @pytest.mark.parametrize("query", ["type:company", "type:community"])
    def test_type_query(self, db_request, query):
        org1 = OrganizationApplicationFactory.create(orgtype=OrganizationType.Company)
        org2 = OrganizationApplicationFactory.create(orgtype=OrganizationType.Community)
        db_request.GET = {"q": query}

        result = views.organization_applications_list(db_request)

        assert result["query"] == query
        assert result["terms"] == [query]

    @pytest.mark.parametrize(
        "status",
        [
            OrganizationApplicationStatus.Submitted,
            OrganizationApplicationStatus.Declined,
            OrganizationApplicationStatus.Deferred,
            OrganizationApplicationStatus.MoreInformationNeeded,
            OrganizationApplicationStatus.Approved,
        ],
    )
    def test_is_query(self, db_request, status):
        org1 = OrganizationApplicationFactory.create(status=status)
        OrganizationApplicationFactory.create(status=OrganizationApplicationStatus.Submitted)
        db_request.GET = {"q": f"is:{status.value}"}

        result = views.organization_applications_list(db_request)

        assert result["query"] == f"is:{status.value}"
        assert result["terms"] == [f"is:{status.value}"]
        # At least one organization should have the matching status
        matching_apps = [app for app in result["organization_applications"] if app.status == status.value]
        assert len(matching_apps) > 0


class TestOrganizationApplicationDetail:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_not_found(self, db_request):
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(lambda *a: None)
        )
        user_service = pretend.stub()
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: {
                views.IOrganizationService: organization_service,
                views.IUserService: user_service,
            }[service]
        )
        db_request.matchdict = {
            "organization_application_id": "00000000-0000-0000-0000-000000000000"
        }

        with pytest.raises(HTTPNotFound):
            views.organization_application_detail(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_get(self, db_request):
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            submitted_by=user
        )
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            )
        )
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda *a: user))
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: {
                views.IOrganizationService: organization_service,
                views.IUserService: user_service,
            }[service]
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.method = "GET"

        result = views.organization_application_detail(db_request)

        assert result["organization_application"] == organization_application
        assert isinstance(result["form"], views.OrganizationApplicationForm)
        assert result["user"] == user

    @pytest.mark.usefixtures("_enable_organizations")
    def test_post(self, db_request):
        user = UserFactory.create()
        organization_application = OrganizationApplicationFactory.create(
            submitted_by=user,
            display_name="Old Name",
        )
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            )
        )
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda *a: user))
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: {
                views.IOrganizationService: organization_service,
                views.IUserService: user_service,
            }[service]
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.method = "POST"
        db_request.POST = {
            "display_name": "New Name",
            "link_url": organization_application.link_url,
            "description": organization_application.description,
            "orgtype": organization_application.orgtype.value,
            "name": organization_application.name,
        }
        db_request.current_route_path = pretend.call_recorder(
            lambda: "/admin/organization_applications/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = pretend.stub()

        result = views.organization_application_detail(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organization_applications/1/"
        assert organization_application.display_name == "New Name"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Application for '{organization_application.name}' updated",
                queue="success",
            )
        ]


@freezegun.freeze_time(datetime.datetime.utcnow())
class TestOrganizationApplicationActions:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization = OrganizationFactory.create(name=organization_application.name)
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            approve_organization_application=pretend.call_recorder(
                lambda *a: organization
            ),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_approve(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/1/"
        assert organization_service.approve_organization_application.calls == [
            pretend.call(organization_application.id, db_request)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization.name}" organization approved',
                queue="success",
            )
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_approve_turbo_mode(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization = OrganizationFactory.create(name=organization_application.name)
        next_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Submitted
        )
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            approve_organization_application=pretend.call_recorder(
                lambda *a: organization
            ),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {"organization_applications_turbo_mode": "true"}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/organization_applications/{kw['organization_application_id']}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_approve(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert (
            result.location
            == f"/admin/organization_applications/{next_application.id}/"
        )

    @pytest.mark.usefixtures("_enable_organizations")
    def test_defer(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            defer_organization_application=pretend.call_recorder(lambda *a: None),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organization_applications/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_defer(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organization_applications/1/"
        assert organization_service.defer_organization_application.calls == [
            pretend.call(organization_application.id, db_request)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization deferred',
                queue="success",
            )
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            request_more_information=pretend.call_recorder(lambda *a: None),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organization_applications/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_request_more_information(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organization_applications/1/"
        assert organization_service.request_more_information.calls == [
            pretend.call(organization_application.id, db_request)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for more info from "{organization_application.name}" '
                "organization sent",
                queue="success",
            )
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_request_more_information_no_message(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            request_more_information=pretend.raiser(ValueError),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organization_applications/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_request_more_information(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organization_applications/1/"
        assert db_request.session.flash.calls == [
            pretend.call("No message provided", queue="error")
        ]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_decline(self, db_request):
        organization_application = OrganizationApplicationFactory.create()
        organization_service = pretend.stub(
            get_organization_application=pretend.call_recorder(
                lambda *a: organization_application
            ),
            decline_organization_application=pretend.call_recorder(lambda *a: None),
        )
        db_request.find_service = pretend.call_recorder(
            lambda service, **kwargs: organization_service
        )
        db_request.matchdict = {
            "organization_application_id": str(organization_application.id)
        }
        db_request.params = {}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organization_applications/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_application_decline(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organization_applications/1/"
        assert organization_service.decline_organization_application.calls == [
            pretend.call(organization_application.id, db_request)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization_application.name}" organization declined',
                queue="success",
            )
        ]


class TestSetUploadLimit:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_with_integer(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["upload_limit"] = "150"

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Upload limit set to 150MiB", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.upload_limit == 150 * views.ONE_MIB

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_with_none(self, db_request):
        organization = OrganizationFactory.create(name="foo")
        organization.upload_limit = 150 * views.ONE_MIB

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["upload_limit"] = ""

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Upload limit set to (default)MiB", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.upload_limit is None

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_with_non_integer(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["upload_limit"] = "meep"

        with pytest.raises(HTTPBadRequest):
            views.set_upload_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_with_less_than_minimum(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.matchdict["organization_id"] = organization.id
        # MAX_FILESIZE is 60 MiB, so 59 MiB < 60 MiB
        db_request.POST["upload_limit"] = "59"

        with pytest.raises(HTTPBadRequest):
            views.set_upload_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_with_greater_than_maximum(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.matchdict["organization_id"] = organization.id
        # UPLOAD_LIMIT_CAP is 1 GiB, so 1025 MiB > 1024 MiB
        db_request.POST["upload_limit"] = "1025"

        with pytest.raises(HTTPBadRequest):
            views.set_upload_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_not_found(self, db_request):
        db_request.matchdict["organization_id"] = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(HTTPNotFound):
            views.set_upload_limit(db_request)


class TestSetTotalSizeLimit:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_with_integer(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["total_size_limit"] = "150"

        result = views.set_total_size_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Total size limit set to 150.0GiB", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.total_size_limit == 150 * views.ONE_GIB

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_with_none(self, db_request):
        organization = OrganizationFactory.create(name="foo")
        organization.total_size_limit = 150 * views.ONE_GIB

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["total_size_limit"] = ""

        result = views.set_total_size_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Total size limit set to (default)GiB", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.total_size_limit is None

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_with_non_integer(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.matchdict["organization_id"] = organization.id
        db_request.POST["total_size_limit"] = "meep"

        with pytest.raises(HTTPBadRequest):
            views.set_total_size_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_with_less_than_minimum(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.matchdict["organization_id"] = organization.id
        # MAX_PROJECT_SIZE is 10 GiB, so 9 GiB < 10 GiB
        db_request.POST["total_size_limit"] = "9"

        with pytest.raises(HTTPBadRequest):
            views.set_total_size_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_not_found(self, db_request):
        db_request.matchdict["organization_id"] = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(HTTPNotFound):
            views.set_total_size_limit(db_request)


class TestAddOrganizationRole:
    def test_add_role(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")

        # Mock record_event
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": "testuser", "role_name": "Manager"}

        result = views.add_organization_role(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Added '{user.username}' as 'Manager' to '{organization.name}'",
                queue="success",
            )
        ]

        # Check role was created
        role = (
            db_request.db.query(OrganizationRole)
            .filter_by(organization=organization, user=user)
            .one()
        )
        assert role.role_name == OrganizationRoleType.Manager

        # Check event was recorded
        assert record_event.calls == [
            pretend.call(
                request=db_request,
                tag="admin:organization:role:add",
                additional={
                    "action": f"add Manager {user.username}",
                    "user_id": str(user.id),
                    "role_name": "Manager",
                },
            )
        ]

    def test_add_role_no_username(self, db_request):
        organization = OrganizationFactory.create(name="pypi")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"role_name": "Manager"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Provide a username", queue="error")
        ]

    def test_add_role_unknown_user(self, db_request):
        organization = OrganizationFactory.create(name="pypi")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": "unknown", "role_name": "Manager"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Unknown username 'unknown'", queue="error")
        ]

    def test_add_role_no_role_name(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": "testuser"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Provide a role", queue="error")
        ]

    def test_add_role_user_already_has_role(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        existing_role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": "testuser", "role_name": "Manager"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"User '{user.username}' already has a role in this organization",
                queue="error",
            )
        ]

    def test_add_role_organization_not_found(self, db_request):
        db_request.matchdict = {"organization_id": "00000000-0000-0000-0000-000000000000"}

        with pytest.raises(HTTPNotFound):
            views.add_organization_role(db_request)


class TestUpdateOrganizationRole:
    def test_update_role(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        # Mock record_event
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"role_name": "Manager"}

        result = views.update_organization_role(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Changed '{user.username}' from 'Member' to 'Manager' "
                f"in '{organization.name}'",
                queue="success",
            )
        ]

        db_request.db.refresh(role)
        assert role.role_name == OrganizationRoleType.Manager

        # Check event was recorded
        assert record_event.calls == [
            pretend.call(
                request=db_request,
                tag="admin:organization:role:change",
                additional={
                    "action": f"change {user.username} from Member to Manager",
                    "user_id": str(user.id),
                    "old_role_name": "Member",
                    "new_role_name": "Manager",
                },
            )
        ]

    def test_update_role_not_found(self, db_request):
        organization = OrganizationFactory.create(name="pypi")

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": "00000000-0000-0000-0000-000000000000",
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.update_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("This role no longer exists", queue="error")
        ]

    def test_update_role_no_role_name(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {}

        result = views.update_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Provide a role", queue="error")
        ]

    def test_update_role_same_role(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"role_name": "Member"}

        result = views.update_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Role is already set to this value", queue="error")
        ]

    def test_update_role_organization_not_found(self, db_request):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000",
            "role_id": "00000000-0000-0000-0000-000000000000",
        }

        with pytest.raises(HTTPNotFound):
            views.update_organization_role(db_request)


class TestDeleteOrganizationRole:
    def test_delete_role(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        # Mock record_event
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": user.username}

        result = views.delete_organization_role(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Removed '{user.username}' as 'Member' from '{organization.name}'",
                queue="success",
            )
        ]

        assert db_request.db.query(OrganizationRole).count() == 0

        # Check event was recorded
        assert record_event.calls == [
            pretend.call(
                request=db_request,
                tag="admin:organization:role:remove",
                additional={
                    "action": f"remove Member {user.username}",
                    "user_id": str(user.id),
                    "role_name": "Member",
                },
            )
        ]

    def test_delete_role_not_found(self, db_request):
        organization = OrganizationFactory.create(name="pypi")

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": "00000000-0000-0000-0000-000000000000",
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.delete_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("This role no longer exists", queue="error")
        ]

    def test_delete_role_wrong_confirmation(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": "wronguser"}

        result = views.delete_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

        # Role should still exist
        assert db_request.db.query(OrganizationRole).count() == 1

    def test_delete_role_no_confirmation(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "role_id": str(role.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {}

        result = views.delete_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

        # Role should still exist
        assert db_request.db.query(OrganizationRole).count() == 1

    def test_delete_role_organization_not_found(self, db_request):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000",
            "role_id": "00000000-0000-0000-0000-000000000000",
        }

        with pytest.raises(HTTPNotFound):
            views.delete_organization_role(db_request)