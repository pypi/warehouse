# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from webob.multidict import MultiDict

from warehouse.admin.views import organizations as views
from warehouse.organizations.models import (
    OrganizationApplicationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService

from ....common.db.accounts import UserFactory
from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationRoleFactory,
    OrganizationStripeCustomerFactory,
)
from ....common.db.subscriptions import StripeCustomerFactory


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
        db_request.route_path = pretend.call_recorder(_organization_application_routes)

        with pytest.raises(HTTPNotFound):
            views.organization_rename(db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_rename(self, db_request):
        admin = UserFactory.create()
        organization = OrganizationFactory.create(name="example")

        db_request.matchdict = {"organization_id": organization.id}
        db_request.params = {
            "new_organization_name": "widget",
        }
        db_request.user = admin
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
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
        db_request.route_path = pretend.call_recorder(_organization_application_routes)
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
