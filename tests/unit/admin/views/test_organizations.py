# SPDX-License-Identifier: Apache-2.0

from datetime import date, timedelta

import pretend
import pytest

from freezegun import freeze_time
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from webob.multidict import MultiDict

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationManualActivationFactory,
    OrganizationOIDCIssuerFactory,
    OrganizationRoleFactory,
    OrganizationStripeCustomerFactory,
)
from tests.common.db.subscriptions import StripeCustomerFactory
from warehouse.admin.views import organizations as views
from warehouse.organizations.models import (
    OIDCIssuerType,
    OrganizationManualActivation,
    OrganizationOIDCIssuer,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService


class TestOrganizationForm:
    def test_validate_success(self):
        form_data = MultiDict(
            {
                "display_name": "My Organization",
                "link_url": "https://example.com",
                "description": "A test organization",
                "orgtype": "Company",
            }
        )
        form = views.OrganizationForm(formdata=form_data)
        assert form.validate(), str(form.errors)

    def test_validate_invalid_url(self):
        form_data = MultiDict(
            {
                "display_name": "My Organization",
                "link_url": "not-a-url",
                "description": "A test organization",
                "orgtype": "Company",
            }
        )
        form = views.OrganizationForm(formdata=form_data)
        assert not form.validate()
        assert "Organization URL must start with http:// or https://" in str(
            form.link_url.errors
        )

    def test_validate_missing_required_fields(self):
        form_data = MultiDict({})
        form = views.OrganizationForm(formdata=form_data)
        assert not form.validate()
        assert form.display_name.errors
        assert form.link_url.errors
        assert form.description.errors
        assert form.orgtype.errors

    def test_validate_field_too_long(self):
        form_data = MultiDict(
            {
                "display_name": "x" * 101,  # Max is 100
                "link_url": "https://example.com/" + "x" * 381,  # Max is 400
                "description": "x" * 401,  # Max is 400
                "orgtype": "Company",
            }
        )
        form = views.OrganizationForm(formdata=form_data)
        assert not form.validate()
        assert "100 characters or less" in str(form.display_name.errors)
        assert "400 characters or less" in str(form.link_url.errors)
        assert "400 characters or less" in str(form.description.errors)


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
    def test_detail(self, db_request):
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
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

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
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_not_found(self, db_request):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }
        db_request.method = "GET"

        with pytest.raises(HTTPNotFound):
            views.organization_detail(db_request)

    def test_updates_organization(self, db_request):
        organization = OrganizationFactory.create(
            display_name="Old Name",
            link_url="https://old-url.com",
            description="Old description",
            orgtype=OrganizationType.Company,
        )
        organization.customer = None  # No Stripe customer

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "display_name": "New Name",
                "link_url": "https://new-url.com",
                "description": "New description",
                "orgtype": "Community",
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda name, **kwargs: f"/admin/organizations/{organization.id}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.organization_detail(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == f"/admin/organizations/{organization.id}/"
        assert organization.display_name == "New Name"
        assert organization.link_url == "https://new-url.com"
        assert organization.description == "New description"
        assert organization.orgtype == OrganizationType.Community
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Organization {organization.name!r} updated successfully",
                queue="success",
            )
        ]

    def test_updates_organization_with_stripe_customer(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(
            name="acme",
            display_name="Old Name",
            link_url="https://old-url.com",
            description="Old description",
            orgtype=OrganizationType.Company,
        )
        stripe_customer = StripeCustomerFactory.create(customer_id="cus_123456")
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "display_name": "New Name",
                "link_url": "https://new-url.com",
                "description": "New description",
                "orgtype": "Community",
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda name, **kwargs: f"/admin/organizations/{organization.id}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.registry = pretend.stub(settings={"site.name": "TestPyPI"})

        # Patch the billing service's update_customer method
        billing_service = db_request.find_service(IBillingService)
        update_customer = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(billing_service, "update_customer", update_customer)

        result = views.organization_detail(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == f"/admin/organizations/{organization.id}/"
        assert organization.display_name == "New Name"
        assert organization.link_url == "https://new-url.com"
        assert organization.description == "New description"
        assert organization.orgtype == OrganizationType.Community
        assert update_customer.calls == [
            pretend.call(
                "cus_123456",
                "TestPyPI Organization - New Name (acme)",
                "New description",
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Organization {organization.name!r} updated successfully",
                queue="success",
            )
        ]

    def test_does_not_update_with_invalid_form(self, db_request):
        organization = OrganizationFactory.create()

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "display_name": "",  # Required field
                "link_url": "invalid-url",  # Invalid URL
                "description": "Some description",
                "orgtype": "Company",
            }
        )

        result = views.organization_detail(db_request)

        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        assert result["form"].errors
        assert "display_name" in result["form"].errors
        assert "link_url" in result["form"].errors

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_with_roles(self, db_request):
        """Test that organization detail view includes roles"""
        organization = OrganizationFactory.create(name="pypi")

        # Create some users with roles
        # Intentionally not ordered to test order later
        user3 = UserFactory.create(username="charlie")
        user2 = UserFactory.create(username="bob")
        user1 = UserFactory.create(username="alice")

        OrganizationRoleFactory.create(
            organization=organization, user=user1, role_name=OrganizationRoleType.Owner
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=user2,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization, user=user3, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)

        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)

        # Check that roles are included and sorted by username
        assert len(result["roles"]) == 3
        assert result["roles"][0].user.username == "alice"
        assert result["roles"][1].user.username == "bob"
        assert result["roles"][2].user.username == "charlie"

        # Check that role forms are created for each role
        assert len(result["role_forms"]) == 3
        assert set(result["role_forms"].keys()) == {role.id for role in result["roles"]}
        for role_id, form in result["role_forms"].items():
            assert isinstance(form, views.OrganizationRoleForm)

        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_detail_no_roles(self, db_request):
        """Test that organization detail view works with no roles"""
        organization = OrganizationFactory.create(name="pypi")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.method = "GET"

        result = views.organization_detail(db_request)

        assert result["organization"] == organization
        assert isinstance(result["form"], views.OrganizationForm)
        assert result["roles"] == []
        assert result["role_forms"] == {}
        assert isinstance(result["add_role_form"], views.AddOrganizationRoleForm)


class TestOrganizationActions:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename_not_found(self, db_request):
        admin = UserFactory.create()

        db_request.matchdict = {
            "organization_id": "deadbeef-dead-beef-dead-beefdeadbeef"
        }
        db_request.params = {
            "new_organization_name": "widget",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        with pytest.raises(HTTPNotFound):
            views.organization_rename(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename(self, db_request):
        admin = UserFactory.create()
        organization = OrganizationFactory.create(name="example")

        db_request.matchdict = {"organization_id": organization.id}
        db_request.params = {
            "new_organization_name": "  widget  ",  # Test trimming whitespace
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/organizations/{organization.id}/"
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_rename(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                '"example" organization renamed "widget"',
                queue="success",
            ),
        ]
        assert result.status_code == 303
        assert result.location == f"/admin/organizations/{organization.id}/"

    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename_fails_on_conflict(self, db_request):
        admin = UserFactory.create()
        OrganizationFactory.create(name="widget")
        organization = OrganizationFactory.create(name="example")

        db_request.matchdict = {"organization_id": organization.id}
        db_request.params = {
            "new_organization_name": "widget",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/organizations/{organization.id}/"
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.organization_rename(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                'Organization name "widget" has been used',
                queue="error",
            ),
        ]
        assert result.status_code == 303
        assert result.location == f"/admin/organizations/{organization.id}/"


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
        db_request.POST = {"username": user.username, "role_name": "Manager"}

        result = views.add_organization_role(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Added '{user.username}' as 'Manager' to '{organization.name}'",
                queue="success",
            )
        ]

        role = db_request.db.query(OrganizationRole).one()
        assert role.role_name == OrganizationRoleType.Manager
        assert role.user == user
        assert role.organization == organization

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
        db_request.POST = {"username": "nonexistent", "role_name": "Manager"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Unknown username 'nonexistent'", queue="error")
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
        db_request.POST = {"username": user.username}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Provide a role", queue="error")
        ]

    def test_add_role_user_already_has_role(self, db_request):
        organization = OrganizationFactory.create(name="pypi")
        user = UserFactory.create(username="testuser")
        OrganizationRoleFactory.create(
            organization=organization, user=user, role_name=OrganizationRoleType.Member
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"username": user.username, "role_name": "Manager"}

        result = views.add_organization_role(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"User '{user.username}' already has a role in this organization",
                queue="error",
            )
        ]

    def test_add_role_organization_not_found(self, db_request):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }

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


class TestManualActivationForm:
    @freeze_time("2024-01-15")
    def test_validate_success(self):
        form_data = MultiDict(
            {
                "seat_limit": "25",
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert form.validate(), str(form.errors)

    @freeze_time("2024-01-15")
    def test_validate_missing_seat_limit(self):
        form_data = MultiDict(
            {
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert not form.validate()
        assert "Specify seat limit" in str(form.seat_limit.errors)

    def test_validate_missing_expires(self):
        form_data = MultiDict(
            {
                "seat_limit": "25",
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert not form.validate()
        assert "Specify expiration date" in str(form.expires.errors)

    @freeze_time("2024-01-15")
    def test_validate_invalid_seat_limit_zero(self):
        form_data = MultiDict(
            {
                "seat_limit": "0",
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert not form.validate()
        assert "Seat limit must be at least 1" in str(form.seat_limit.errors)

    @freeze_time("2024-01-15")
    def test_validate_invalid_seat_limit_negative(self):
        form_data = MultiDict(
            {
                "seat_limit": "-1",
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert not form.validate()
        assert "Seat limit must be at least 1" in str(form.seat_limit.errors)

    @freeze_time("2024-01-15")
    def test_validate_expires_in_past(self):
        form_data = MultiDict(
            {
                "seat_limit": "25",
                "expires": "2020-01-01",
            }
        )
        form = views.ManualActivationForm(formdata=form_data)
        assert not form.validate()
        assert "Expiration date must be in the future" in str(form.expires.errors)


class TestAddManualActivation:
    @freeze_time("2024-01-15")
    def test_add_manual_activation_success(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        user = UserFactory.create()

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "seat_limit": "25",
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        organization.record_event = pretend.call_recorder(lambda *a, **kw: None)

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.add_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check that manual activation was created
        manual_activation = db_request.db.query(OrganizationManualActivation).first()
        assert manual_activation is not None
        assert manual_activation.organization_id == organization.id
        assert manual_activation.seat_limit == 25
        assert manual_activation.created_by_id == user.id

        # Check success flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert call.args[0].startswith("Manual activation added for")
        assert call.kwargs == {"queue": "success"}

        # Check event was recorded
        assert len(organization.record_event.calls) == 1
        call = organization.record_event.calls[0]
        assert call.kwargs["tag"] == "admin:organization:manual_activation:add"

    def test_add_manual_activation_organization_not_found(
        self, db_request, monkeypatch
    ):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: None)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        with pytest.raises(HTTPNotFound):
            views.add_manual_activation(db_request)

    @freeze_time("2024-01-15")
    def test_add_manual_activation_already_exists(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationManualActivationFactory.create(organization=organization)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "seat_limit": "25",
                "expires": (date.today() + timedelta(days=365)).isoformat(),
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.add_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check error flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert "already has manual activation" in call.args[0]
        assert call.kwargs == {"queue": "error"}

    @freeze_time("2024-01-15")
    def test_add_manual_activation_invalid_form(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        user = UserFactory.create()

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "seat_limit": "0",  # Invalid
                "expires": (
                    date.today() - timedelta(days=365)
                ).isoformat(),  # In the past
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.add_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check error flash messages for validation errors
        assert len(db_request.session.flash.calls) >= 1
        error_messages = [call.args[0] for call in db_request.session.flash.calls]
        error_messages = " ".join(error_messages)
        assert "seat_limit" in error_messages or "expires" in error_messages


class TestUpdateManualActivation:
    @freeze_time("2024-01-15")
    def test_update_manual_activation_success(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        manual_activation = OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=10,
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "seat_limit": "50",
                "expires": (date.today() + timedelta(days=730)).isoformat(),
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        organization.record_event = pretend.call_recorder(lambda *a, **kw: None)

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.update_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check that manual activation was updated
        db_request.db.refresh(manual_activation)
        assert manual_activation.seat_limit == 50
        # created_by_id should NOT change during update - it stays the original creator
        assert manual_activation.created_by_id != user.id

        # Check success flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert call.args[0].startswith("Manual activation updated for")
        assert call.kwargs == {"queue": "success"}

        # Check event was recorded
        assert len(organization.record_event.calls) == 1
        call = organization.record_event.calls[0]
        assert call.kwargs["tag"] == "admin:organization:manual_activation:update"

    def test_update_manual_activation_not_found(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.POST = MultiDict(
            {
                "seat_limit": "50",
                "expires": (date.today() + timedelta(days=730)).isoformat(),
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.update_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check error flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert "has no manual activation to update" in call.args[0]
        assert call.kwargs == {"queue": "error"}

    @freeze_time("2024-01-15")
    def test_update_manual_activation_invalid_form(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=10,
        )

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = user
        # Invalid form data - seat limit is negative
        db_request.POST = MultiDict(
            {
                "seat_limit": "-5",
                "expires": (date.today() + timedelta(days=730)).isoformat(),
            }
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.update_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check that form validation errors were flashed
        assert len(db_request.session.flash.calls) >= 1
        # Should have flashed seat_limit error
        error_flashed = any(
            "seat_limit" in call.args[0]
            for call in db_request.session.flash.calls
            if call.kwargs.get("queue") == "error"
        )
        assert error_flashed

    def test_update_manual_activation_organization_not_found(
        self, db_request, monkeypatch
    ):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: None)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        with pytest.raises(HTTPNotFound):
            views.update_manual_activation(db_request)


class TestDeleteManualActivation:
    def test_delete_manual_activation_success(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="test-org")
        OrganizationManualActivationFactory.create(organization=organization)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.POST = MultiDict({"confirm": "test-org"})
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        organization.record_event = pretend.call_recorder(lambda *a, **kw: None)

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.delete_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check that manual activation was deleted
        remaining_activations = (
            db_request.db.query(OrganizationManualActivation)
            .filter(OrganizationManualActivation.organization_id == organization.id)
            .count()
        )
        assert remaining_activations == 0

        # Check success flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert "Manual activation removed from" in call.args[0]
        assert call.kwargs == {"queue": "success"}

        # Check event was recorded
        assert len(organization.record_event.calls) == 1
        call = organization.record_event.calls[0]
        assert call.kwargs["tag"] == "admin:organization:manual_activation:delete"

    def test_delete_manual_activation_no_confirmation(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="test-org")
        OrganizationManualActivationFactory.create(organization=organization)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.POST = MultiDict({"confirm": "wrong-name"})
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.delete_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check error flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert call.args[0] == "Confirm the request"
        assert call.kwargs == {"queue": "error"}

        # Manual activation should still exist

        remaining_activations = (
            db_request.db.query(OrganizationManualActivation)
            .filter(OrganizationManualActivation.organization_id == organization.id)
            .count()
        )
        assert remaining_activations == 1

    def test_delete_manual_activation_not_found(self, db_request, monkeypatch):
        organization = OrganizationFactory.create(name="test-org")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.POST = MultiDict({"confirm": "test-org"})
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: organization)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        result = views.delete_manual_activation(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Check error flash message
        assert len(db_request.session.flash.calls) == 1
        call = db_request.session.flash.calls[0]
        assert "has no manual activation to delete" in call.args[0]
        assert call.kwargs == {"queue": "error"}

    def test_delete_manual_activation_organization_not_found(
        self, db_request, monkeypatch
    ):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }

        organization_service = pretend.stub(
            get_organization=pretend.call_recorder(lambda id: None)
        )
        monkeypatch.setattr(
            db_request, "find_service", lambda iface, context: organization_service
        )

        with pytest.raises(HTTPNotFound):
            views.delete_manual_activation(db_request)


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
        db_request.POST = MultiDict({"upload_limit": "150"})

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Upload limit set to 150.0MiB", queue="success")
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
        db_request.POST = MultiDict({"upload_limit": ""})

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Upload limit set to (default)", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.upload_limit is None

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_invalid_value(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST = MultiDict({"upload_limit": "not_an_integer"})

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "upload_limit: Upload limit must be a valid integer or empty",
                queue="error",
            )
        ]
        assert result.status_code == 303

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_not_found(self, db_request):
        db_request.matchdict["organization_id"] = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(HTTPNotFound):
            views.set_upload_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_above_cap(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST = MultiDict({"upload_limit": "2048"})  # 2048 MiB > 1024 MiB cap

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "upload_limit: Upload limit can not be greater than 1024.0MiB",
                queue="error",
            )
        ]
        assert result.status_code == 303

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_upload_limit_below_default(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST = MultiDict({"upload_limit": "50"})  # 50 MiB < 100 MiB default

        result = views.set_upload_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "upload_limit: Upload limit can not be less than 100.0MiB",
                queue="error",
            )
        ]
        assert result.status_code == 303


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
        db_request.POST = MultiDict({"total_size_limit": "150"})

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
        db_request.POST = MultiDict({"total_size_limit": ""})

        result = views.set_total_size_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Total size limit set to (default)", queue="success")
        ]
        assert result.status_code == 303
        assert result.location == "/admin/organizations/1/"
        assert organization.total_size_limit is None

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_invalid_value(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST = MultiDict({"total_size_limit": "not_an_integer"})

        result = views.set_total_size_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "total_size_limit: Total size limit must be a valid integer or empty",
                queue="error",
            )
        ]
        assert result.status_code == 303

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_not_found(self, db_request):
        db_request.matchdict["organization_id"] = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(HTTPNotFound):
            views.set_total_size_limit(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_set_total_size_limit_below_default(self, db_request):
        organization = OrganizationFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda a, organization_id: "/admin/organizations/1/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.matchdict["organization_id"] = organization.id
        db_request.POST = MultiDict({"total_size_limit": "5"})  # 5 GiB < 10 GiB default

        result = views.set_total_size_limit(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "total_size_limit: Total organization size can not be less than "
                "10.0GiB",
                queue="error",
            )
        ]
        assert result.status_code == 303


class TestAddOIDCIssuer:
    def test_add_oidc_issuer_success(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        # Mock record_event
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = admin_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "issuer_type": "gitlab",
                "issuer_url": "https://gitlab.company.com",
            }
        )

        result = views.add_oidc_issuer(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                "OIDC issuer 'https://gitlab.company.com' (gitlab) added to "
                f"'{organization.name}'",
                queue="success",
            )
        ]

        issuer = db_request.db.query(OrganizationOIDCIssuer).one()
        assert issuer.issuer_type == OIDCIssuerType.GitLab
        assert issuer.issuer_url == "https://gitlab.company.com"
        assert issuer.organization == organization
        assert issuer.created_by == admin_user

        # Check event was recorded
        assert record_event.calls == [
            pretend.call(
                request=db_request,
                tag="admin:organization:oidc_issuer:add",
                additional={
                    "issuer_type": "gitlab",
                    "issuer_url": "https://gitlab.company.com",
                },
            )
        ]

    def test_add_oidc_issuer_invalid_form(self, db_request):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = admin_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        # Missing issuer_url
        db_request.POST = MultiDict({"issuer_type": "gitlab"})

        result = views.add_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Should flash form validation errors
        assert len(db_request.session.flash.calls) > 0
        assert "error" in str(db_request.session.flash.calls[0])

    def test_add_oidc_issuer_invalid_url(self, db_request):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = admin_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        # Invalid URL (not https)
        db_request.POST = MultiDict(
            {
                "issuer_type": "gitlab",
                "issuer_url": "http://gitlab.company.com",
            }
        )

        result = views.add_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        # Should flash form validation errors
        flash_messages = [call.args[0] for call in db_request.session.flash.calls]
        assert any("https://" in msg for msg in flash_messages)

    def test_add_oidc_issuer_duplicate(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        # Create existing issuer
        OrganizationOIDCIssuerFactory.create(
            organization=organization,
            issuer_type=OIDCIssuerType.GitLab,
            issuer_url="https://gitlab.company.com",
            created_by=admin_user,
        )

        # Mock record_event (should not be called on duplicate)
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {"organization_id": str(organization.id)}
        db_request.user = admin_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "issuer_type": "gitlab",
                "issuer_url": "https://gitlab.company.com",
            }
        )

        result = views.add_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Issuer 'https://gitlab.company.com' already exists "
                f"for organization '{organization.name}'",
                queue="error",
            )
        ]

        # No new event recorded
        assert record_event.calls == []

    def test_add_oidc_issuer_organization_not_found(self, db_request):
        admin_user = UserFactory.create(username="admin")

        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000"
        }
        db_request.user = admin_user

        with pytest.raises(HTTPNotFound):
            views.add_oidc_issuer(db_request)


class TestDeleteOIDCIssuer:
    def test_delete_oidc_issuer_success(self, db_request, monkeypatch):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        issuer = OrganizationOIDCIssuerFactory.create(
            organization=organization,
            issuer_type=OIDCIssuerType.GitLab,
            issuer_url="https://gitlab.company.com",
            created_by=admin_user,
        )

        # Mock record_event
        record_event = pretend.call_recorder(lambda **kwargs: None)
        monkeypatch.setattr(organization, "record_event", record_event)

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "issuer_id": str(issuer.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({"confirm": "https://gitlab.company.com"})

        result = views.delete_oidc_issuer(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/admin/organizations/"

        assert db_request.session.flash.calls == [
            pretend.call(
                "OIDC issuer 'https://gitlab.company.com' removed "
                f"from '{organization.name}'",
                queue="success",
            )
        ]

        assert db_request.db.query(OrganizationOIDCIssuer).count() == 0

        # Check event was recorded
        assert record_event.calls == [
            pretend.call(
                request=db_request,
                tag="admin:organization:oidc_issuer:delete",
                additional={
                    "issuer_type": "gitlab",
                    "issuer_url": "https://gitlab.company.com",
                },
            )
        ]

    def test_delete_oidc_issuer_not_found(self, db_request):
        organization = OrganizationFactory.create()

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "issuer_id": "00000000-0000-0000-0000-000000000000",
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({"confirm": "https://gitlab.company.com"})

        result = views.delete_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("This issuer does not exist", queue="error")
        ]

    def test_delete_oidc_issuer_wrong_confirmation(self, db_request):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        issuer = OrganizationOIDCIssuerFactory.create(
            organization=organization,
            issuer_type=OIDCIssuerType.GitLab,
            issuer_url="https://gitlab.company.com",
            created_by=admin_user,
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "issuer_id": str(issuer.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({"confirm": "https://wrong-url.com"})

        result = views.delete_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

        # Issuer should still exist
        assert db_request.db.query(OrganizationOIDCIssuer).count() == 1

    def test_delete_oidc_issuer_no_confirmation(self, db_request):
        organization = OrganizationFactory.create()
        admin_user = UserFactory.create(username="admin")

        issuer = OrganizationOIDCIssuerFactory.create(
            organization=organization,
            issuer_type=OIDCIssuerType.GitLab,
            issuer_url="https://gitlab.company.com",
            created_by=admin_user,
        )

        db_request.matchdict = {
            "organization_id": str(organization.id),
            "issuer_id": str(issuer.id),
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/organizations/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({})

        result = views.delete_oidc_issuer(db_request)
        assert isinstance(result, HTTPSeeOther)

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

        # Issuer should still exist
        assert db_request.db.query(OrganizationOIDCIssuer).count() == 1

    def test_delete_oidc_issuer_organization_not_found(self, db_request):
        db_request.matchdict = {
            "organization_id": "00000000-0000-0000-0000-000000000000",
            "issuer_id": "00000000-0000-0000-0000-000000000001",
        }

        with pytest.raises(HTTPNotFound):
            views.delete_oidc_issuer(db_request)
