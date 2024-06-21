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
import datetime
import uuid

import pretend
import pytest

from freezegun import freeze_time
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import (
    OrganizationEventFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
    TeamFactory,
)
from tests.common.db.packaging import ProjectFactory, RoleFactory
from tests.common.db.subscriptions import (
    StripeCustomerFactory,
    StripeSubscriptionFactory,
    StripeSubscriptionPriceFactory,
)
from warehouse.accounts import ITokenService, IUserService
from warehouse.accounts.interfaces import TokenExpired
from warehouse.authnz import Permissions
from warehouse.manage import views
from warehouse.manage.views import organizations as org_views
from warehouse.organizations import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.packaging import Project
from warehouse.utils.paginate import paginate_url_factory


class TestManageOrganizations:
    def test_default_response(self, monkeypatch):
        create_organization_application_obj = pretend.stub()
        create_organization_application_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_application_obj
        )
        monkeypatch.setattr(
            org_views,
            "CreateOrganizationApplicationForm",
            create_organization_application_cls,
        )

        organization = pretend.stub(name=pretend.stub(), is_approved=None)

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [],
                "organizations_owned": [organization],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(org_views, "user_organizations", user_organizations)

        organization_service = pretend.stub(
            get_organizations_by_user=lambda *a, **kw: [organization],
            get_organization_invites_by_user=lambda *a, **kw: [],
        )
        user_service = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(
                id=pretend.stub(), username=pretend.stub(), organization_applications=[]
            ),
            find_service=lambda interface, **kw: {
                IOrganizationService: organization_service,
                IUserService: user_service,
            }[interface],
            registry=pretend.stub(
                settings={
                    "warehouse.organizations.max_undecided_organization_applications": 3
                }
            ),
        )

        view = org_views.ManageOrganizationsViews(request)

        assert view.default_response == {
            "organization_applications": [],
            "organization_invites": [],
            "organizations": [organization],
            "organizations_managed": [],
            "organizations_owned": [organization.name],
            "organizations_billing": [],
            "create_organization_application_form": create_organization_application_obj,
        }

    def test_manage_organizations(self, monkeypatch):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            organization_access=True,
            user=pretend.stub(),
        )

        default_response = MultiDict({"default": "response"})
        monkeypatch.setattr(
            org_views.ManageOrganizationsViews,
            "default_response",
            default_response,
        )
        view = org_views.ManageOrganizationsViews(request)
        result = view.manage_organizations()

        assert result == default_response

    def test_manage_organizations_disable_organizations(self):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            organization_access=False,
        )

        view = org_views.ManageOrganizationsViews(request)
        with pytest.raises(HTTPNotFound):
            view.manage_organizations()

    def test_create_organization_application(self, enable_organizations, monkeypatch):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
        )

        organization = pretend.stub(
            id=pretend.stub(),
            name="psf",
            display_name="Python Software Foundation",
            orgtype="Community",
            link_url="https://www.python.org/psf/",
            description=(
                "To promote, protect, and advance the Python programming "
                "language, and to support and facilitate the growth of a "
                "diverse and international community of Python programmers"
            ),
            is_active=False,
            is_approved=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization
            ),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
        )

        request = pretend.stub(
            POST={
                "name": organization.name,
                "display_name": organization.display_name,
                "orgtype": organization.orgtype,
                "link_url": organization.link_url,
                "description": organization.description,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            organization_access=True,
            remote_addr="0.0.0.0",
            ip_address=pretend.stub(
                ip_address="0.0.0.0",
                hashed_ip_address="deadbeef",
                geoip_info={"country_code": "US"},
            ),
            path="request-path",
            registry=pretend.stub(
                settings={
                    "warehouse.organizations.max_undecided_organization_applications": 3
                }
            ),
        )

        create_organization_application_obj = pretend.stub(
            data=request.POST,
            orgtype=pretend.stub(data=request.POST["orgtype"]),
            validate=lambda: True,
        )
        create_organization_application_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_application_obj
        )
        monkeypatch.setattr(
            org_views,
            "CreateOrganizationApplicationForm",
            create_organization_application_cls,
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_new_organization_requested_email", send_email
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            org_views.ManageOrganizationsViews,
            "default_response",
            default_response,
        )

        view = org_views.ManageOrganizationsViews(request)
        result = view.create_organization_application()

        assert user_service.get_admins.calls == []
        assert organization_service.add_organization_application.calls == [
            pretend.call(
                name=organization.name,
                display_name=organization.display_name,
                orgtype=organization.orgtype,
                link_url=organization.link_url,
                description=organization.description,
                submitted_by=request.user,
            )
        ]
        assert organization_service.add_organization_role.calls == []
        assert organization.record_event.calls == []
        assert request.user.record_event.calls == []
        assert send_email.calls == [
            pretend.call(
                request,
                request.user,
                organization_name=organization.name,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_create_organization_application_with_subscription(
        self, enable_organizations, monkeypatch
    ):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
        )

        organization = pretend.stub(
            id=pretend.stub(),
            name="psf",
            normalized_name="psf",
            display_name="Python Software Foundation",
            orgtype="Company",
            link_url="https://www.python.org/psf/",
            description=(
                "To promote, protect, and advance the Python programming "
                "language, and to support and facilitate the growth of a "
                "diverse and international community of Python programmers"
            ),
            is_active=False,
            is_approved=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization
            ),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
        )

        request = pretend.stub(
            POST={
                "name": organization.name,
                "display_name": organization.display_name,
                "orgtype": organization.orgtype,
                "link_url": organization.link_url,
                "description": organization.description,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            organization_access=True,
            remote_addr="0.0.0.0",
            ip_address=pretend.stub(
                ip_address="0.0.0.0",
                hashed_ip_address="deadbeef",
                geoip_info={"country_code": "US"},
            ),
            route_path=lambda *a, **kw: "manage-subscription-url",
            path="request-path",
            registry=pretend.stub(
                settings={
                    "warehouse.organizations.max_undecided_organization_applications": 3
                }
            ),
        )

        create_organization_application_obj = pretend.stub(
            data=request.POST,
            orgtype=pretend.stub(data=request.POST["orgtype"]),
            validate=lambda: True,
        )
        create_organization_application_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_application_obj
        )
        monkeypatch.setattr(
            org_views,
            "CreateOrganizationApplicationForm",
            create_organization_application_cls,
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_new_organization_requested_email", send_email
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            org_views.ManageOrganizationsViews,
            "default_response",
            default_response,
        )

        view = org_views.ManageOrganizationsViews(request)
        result = view.create_organization_application()

        assert user_service.get_admins.calls == []
        assert organization_service.add_organization_application.calls == [
            pretend.call(
                name=organization.name,
                display_name=organization.display_name,
                orgtype=organization.orgtype,
                link_url=organization.link_url,
                description=organization.description,
                submitted_by=request.user,
            )
        ]
        assert organization_service.add_organization_role.calls == []
        assert organization.record_event.calls == []
        assert request.user.record_event.calls == []
        assert send_email.calls == [
            pretend.call(
                request,
                request.user,
                organization_name=organization.name,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "request-path"

    def test_create_organization_application_validation_fails(self, monkeypatch):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
        )

        organization = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization_application=pretend.call_recorder(
                lambda *a, **kw: organization
            ),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
        )

        request = pretend.stub(
            POST={
                "name": None,
                "display_name": None,
                "orgtype": None,
                "link_url": None,
                "description": None,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            organization_access=True,
            remote_addr="0.0.0.0",
            ip_address=pretend.stub(
                ip_address="0.0.0.0",
                hashed_ip_address="deadbeef",
                geoip_info={"country_code": "US"},
            ),
            registry=pretend.stub(
                settings={
                    "warehouse.organizations.max_undecided_organization_applications": 3
                }
            ),
        )

        create_organization_application_obj = pretend.stub(
            validate=lambda: False, data=request.POST
        )
        create_organization_application_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_application_obj
        )
        monkeypatch.setattr(
            org_views,
            "CreateOrganizationApplicationForm",
            create_organization_application_cls,
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_new_organization_requested_email", send_email
        )

        view = org_views.ManageOrganizationsViews(request)
        result = view.create_organization_application()

        assert user_service.get_admins.calls == []
        assert organization_service.add_organization_application.calls == []
        assert organization_service.add_catalog_entry.calls == []
        assert organization_service.add_organization_role.calls == []
        assert organization.record_event.calls == []
        assert send_email.calls == []
        assert result == {
            "create_organization_application_form": create_organization_application_obj
        }

    def test_create_organization_application_disable_organizations(self):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            organization_access=False,
        )

        view = org_views.ManageOrganizationsViews(request)
        with pytest.raises(HTTPNotFound):
            view.create_organization_application()


class TestManageOrganizationSettings:
    def test_manage_organization(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        db_request.user = pretend.stub()
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            org_views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.manage_organization()

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "save_organization_form": save_organization_obj,
            "save_organization_name_form": save_organization_name_obj,
            "active_projects": view.active_projects,
        }
        assert save_organization_cls.calls == [
            pretend.call(
                MultiDict(
                    {
                        "name": organization.name,
                        "display_name": organization.display_name,
                        "link_url": organization.link_url,
                        "description": organization.description,
                        "orgtype": organization.orgtype,
                    }
                )
            ),
        ]

    @pytest.mark.parametrize(
        ["orgtype", "has_customer"],
        [(orgtype, True) for orgtype in list(OrganizationType)]
        + [(orgtype, False) for orgtype in list(OrganizationType)],
    )
    def test_save_organization(
        self,
        db_request,
        pyramid_user,
        orgtype,
        has_customer,
        billing_service,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(orgtype=orgtype)
        customer = StripeCustomerFactory.create()
        if has_customer:
            OrganizationStripeCustomerFactory.create(
                organization=organization, customer=customer
            )
        db_request.POST = {
            "display_name": organization.display_name,
            "link_url": organization.link_url,
            "description": organization.description,
            "orgtype": organization.orgtype,
        }

        db_request.registry.settings["site.name"] = "PiePeaEye"

        monkeypatch.setattr(
            organization_service,
            "update_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            billing_service,
            "update_customer",
            pretend.call_recorder(lambda stripe_customer_id, name, description: None),
        )

        save_organization_obj = pretend.stub(
            validate=lambda: True, data=db_request.POST
        )
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(org_views, "send_organization_updated_email", send_email)
        monkeypatch.setattr(
            org_views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert isinstance(result, HTTPSeeOther)
        assert organization_service.update_organization.calls == [
            pretend.call(organization.id, **db_request.POST)
        ]
        assert billing_service.update_customer.calls == (
            [
                pretend.call(
                    customer.customer_id,
                    (
                        f"PiePeaEye Organization - {organization.display_name} "
                        f"({organization.name})"
                    ),
                    organization.description,
                )
            ]
            if has_customer
            else []
        )
        assert send_email.calls == [
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name=organization.name,
                organization_display_name=organization.display_name,
                organization_link_url=organization.link_url,
                organization_description=organization.description,
                organization_orgtype=organization.orgtype,
                previous_organization_display_name=organization.display_name,
                previous_organization_link_url=organization.link_url,
                previous_organization_description=organization.description,
                previous_organization_orgtype=organization.orgtype,
            ),
        ]

    def test_save_organization_validation_fails(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create()
        db_request.POST = {
            "display_name": organization.display_name,
            "link_url": organization.link_url,
            "description": organization.description,
            "orgtype": organization.orgtype,
        }
        db_request.user = pretend.stub()

        monkeypatch.setattr(
            organization_service,
            "update_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        save_organization_obj = pretend.stub(
            validate=lambda: False, data=db_request.POST
        )
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            org_views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert result == {
            **view.default_response,
            "save_organization_form": save_organization_obj,
        }
        assert organization_service.update_organization.calls == []

    def test_save_organization_name(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name,
            "name": "FooBar",
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, organization_name, **kw: (
                f"/manage/organization/{organization_name}/settings/"
            )
        )

        def rename_organization(organization_id, organization_name):
            organization.name = organization_name

        monkeypatch.setattr(
            organization_service,
            "rename_organization",
            pretend.call_recorder(rename_organization),
        )

        admin = None
        monkeypatch.setattr(
            user_service,
            "get_admin_user",
            pretend.call_recorder(lambda *a, **kw: admin),
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub(
            validate=lambda: True, name=pretend.stub(data=db_request.POST["name"])
        )
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            org_views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_admin_organization_renamed_email", send_email
        )
        monkeypatch.setattr(org_views, "send_organization_renamed_email", send_email)
        monkeypatch.setattr(
            org_views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization_name()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == (
            f"/manage/organization/{organization.normalized_name}/settings/#modal-close"
        )
        assert organization_service.rename_organization.calls == [
            pretend.call(organization.id, "FooBar")
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admin,
                organization_name="FooBar",
                previous_organization_name="foobar",
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name="FooBar",
                previous_organization_name="foobar",
            ),
        ]

    def test_save_organization_name_wrong_confirm(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name.upper(),
            "name": "FooBar",
        }
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        with pytest.raises(HTTPSeeOther):
            view.save_organization_name()

        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "Could not rename organization - "
                    "'FOOBAR' is not the same as 'foobar'"
                ),
                queue="error",
            )
        ]

    def test_save_organization_name_validation_fails(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name,
            "name": "FooBar",
        }
        db_request.user = pretend.stub()

        def rename_organization(organization_id, organization_name):
            organization.name = organization_name

        monkeypatch.setattr(
            organization_service,
            "rename_organization",
            pretend.call_recorder(rename_organization),
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub(
            validate=lambda: False, errors=pretend.stub(values=lambda: ["Invalid"])
        )
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            org_views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization_name()

        assert result == {
            **view.default_response,
            "save_organization_name_form": save_organization_name_obj,
        }
        assert organization_service.rename_organization.calls == []

    def test_delete_organization(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        admin = None
        monkeypatch.setattr(
            user_service,
            "get_admin_user",
            pretend.call_recorder(lambda *a, **kw: admin),
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_admin_organization_deleted_email", send_email
        )
        monkeypatch.setattr(org_views, "send_organization_deleted_email", send_email)
        monkeypatch.setattr(
            org_views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        assert organization_service.delete_organization.calls == [
            pretend.call(organization.id)
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admin,
                organization_name=organization.name,
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name=organization.name,
            ),
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_delete_organization_with_active_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(org_views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            org_views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert result == view.default_response
        assert organization_service.delete_organization.calls == []
        assert db_request.route_path.calls == []

    def test_delete_organization_with_subscriptions(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        admin = None
        monkeypatch.setattr(
            user_service,
            "get_admin_user",
            pretend.call_recorder(lambda *a, **kw: admin),
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_admin_organization_deleted_email", send_email
        )
        monkeypatch.setattr(org_views, "send_organization_deleted_email", send_email)
        monkeypatch.setattr(
            org_views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        assert organization_service.delete_organization.calls == [
            pretend.call(organization.id)
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admin,
                organization_name=organization.name,
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name=organization.name,
            ),
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]


class TestManageOrganizationBillingViews:
    @pytest.fixture
    def organization(self):
        organization = OrganizationFactory.create()
        OrganizationStripeCustomerFactory.create(organization=organization)
        return organization

    @pytest.fixture
    def organization_no_customer(self):
        return OrganizationFactory.create()

    @pytest.fixture
    def subscription(self, organization):
        return StripeSubscriptionFactory.create(
            stripe_customer_id=organization.customer.customer_id
        )

    @pytest.fixture
    def organization_subscription(self, organization, subscription):
        return OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

    @pytest.fixture
    def subscription_price(self):
        return StripeSubscriptionPriceFactory.create()

    def test_customer_id(
        self,
        db_request,
        subscription_service,
        organization,
    ):
        billing_service = pretend.stub(
            create_customer=lambda *a, **kw: {"id": organization.customer.customer_id},
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        customer_id = view.customer_id

        assert customer_id == organization.customer.customer_id

    def test_customer_id_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization_no_customer,
    ):
        db_request.registry.settings["site.name"] = "PyPI"

        view = org_views.ManageOrganizationBillingViews(
            organization_no_customer, db_request
        )
        customer_id = view.customer_id

        assert customer_id.startswith("mockcus_")

    def test_disable_organizations(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
    ):
        db_request.organization_access = False
        view = org_views.ManageOrganizationBillingViews(organization, db_request)

        with pytest.raises(HTTPNotFound):
            view.create_or_manage_subscription()

    def test_activate_subscription(
        self,
        db_request,
        organization,
        enable_organizations,
    ):
        view = org_views.ManageOrganizationBillingViews(organization, db_request)

        # We're not ready for companies to activate their own subscriptions yet.
        with pytest.raises(HTTPNotFound):
            assert view.activate_subscription()

        # result = view.activate_subscription()

        # assert result == {"organization": organization}

    def test_create_subscription(
        self,
        db_request,
        subscription_service,
        organization,
        subscription_price,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Stub for billing service is not instance of MockStripeBillingService.
        create_checkout_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )

        billing_service = pretend.stub(
            create_checkout_session=create_checkout_session,
            create_customer=lambda *a, **kw: {"id": organization.customer.customer_id},
            sync_price=lambda *a, **kw: None,
            sync_product=lambda *a, **kw: None,
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        result = view.create_or_manage_subscription()

        assert create_checkout_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                price_ids=[subscription_price.price_id],
                success_url=view.return_url,
                cancel_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_create_subscription_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        subscription_price,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Fixture for billing service is instance of MockStripeBillingService.
        create_checkout_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        monkeypatch.setattr(
            billing_service, "create_checkout_session", create_checkout_session
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        assert create_checkout_session.calls == [
            pretend.call(
                customer_id=view.customer_id,
                price_ids=[subscription_price.price_id],
                success_url=view.return_url,
                cancel_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"

    def test_manage_subscription(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        organization_subscription,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Stub for billing service is not instance of MockStripeBillingService.
        create_portal_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        billing_service = pretend.stub(
            create_portal_session=create_portal_session,
            sync_price=lambda *a, **kw: None,
            sync_product=lambda *a, **kw: None,
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        result = view.create_or_manage_subscription()

        assert create_portal_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                return_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_manage_subscription_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        organization_subscription,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Fixture for billing service is instance of MockStripeBillingService.
        create_portal_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        monkeypatch.setattr(
            billing_service, "create_portal_session", create_portal_session
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        assert create_portal_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                return_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"


class TestManageOrganizationTeams:
    def test_manage_teams(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create()]

        db_request.POST = MultiDict()

        view = org_views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.manage_teams()
        form = result["create_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "create_team_form": form,
        }

    def test_create_team(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create()]

        db_request.POST = MultiDict({"name": "Team Name"})

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        def add_team(name, *args, **kwargs):
            team = TeamFactory.create(name=name)
            organization.teams.append(team)
            return team

        monkeypatch.setattr(organization_service, "add_team", add_team)

        send_team_created_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views,
            "send_team_created_email",
            send_team_created_email,
        )

        view = org_views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.create_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(organization.teams) == 2
        assert organization.teams[-1].name == "Team Name"
        assert send_team_created_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                team_name="Team Name",
            )
        ]

    def test_create_team_invalid(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create(name="Used Name")]

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        db_request.POST = MultiDict({"name": "Used Name"})

        view = org_views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.create_team()
        form = result["create_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "create_team_form": form,
        }
        assert form.name.errors == [
            "This team name has already been used. Choose a different team name."
        ]
        assert len(organization.teams) == 1


class TestManageOrganizationProjects:
    def test_manage_organization_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        add_organization_project_obj = pretend.stub()
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.manage_organization_projects()

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": set(),
            "projects_sole_owned": set(),
            "add_organization_project_form": add_organization_project_obj,
        }
        assert len(add_organization_project_cls.calls) == 1

    def test_add_organization_project_existing_project(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 2
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
            )
        ]

    def test_add_organization_project_existing_project_no_individual_owner(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 2
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
            )
        ]

    def test_add_organization_project_existing_project_invalid(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: False,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "add_organization_project_form": add_organization_project_obj,
        }
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 1

    def test_add_organization_project_new_project(
        self,
        db_request,
        pyramid_user,
        enable_organizations,
        monkeypatch,
    ):
        db_request.help_url = lambda *a, **kw: ""

        organization = OrganizationFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data="fakepackage"),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        # The project was created
        project = db_request.db.query(Project).filter_by(name="fakepackage").one()

        # Refresh the project in the DB session to ensure it is not stale
        db_request.db.refresh(project)

        # The project belongs to the organization.
        assert project.organization == organization

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name="fakepackage",
            )
        ]

    @pytest.mark.parametrize(
        "invalid_name, expected",
        [
            ("-invalid-name-", "The name '-invalid-name-' is invalid."),
            (
                "requirements.txt",
                (
                    "The name 'requirements.txt' isn't allowed. See help-url "
                    "for more information."
                ),
            ),
        ],
    )
    def test_add_organization_project_new_project_exception(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
        invalid_name,
        expected,
    ):
        db_request.help_url = lambda *a, **kw: "help-url"

        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data=invalid_name, errors=[]),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "add_organization_project_form": add_organization_project_obj,
        }
        assert add_organization_project_obj.new_project_name.errors == [expected]
        assert len(organization.projects) == 1

    def test_add_organization_project_new_project_name_conflict(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        db_request.help_url = lambda *a, **kw: "help-url"

        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data=project.name, errors=[]),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            org_views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "add_organization_project_form": add_organization_project_obj,
        }
        assert add_organization_project_obj.new_project_name.errors == [
            (
                "The name {name!r} conflicts with an existing project. "
                "See {projecthelp} for more information."
            ).format(
                name=project.name,
                projecthelp="help-url",
            )
        ]
        assert len(organization.projects) == 1


class TestManageOrganizationRoles:
    def test_get_manage_organization_roles(
        self, db_request, pyramid_user, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        form_obj = pretend.stub()

        def form_class(*a, **kw):
            return form_obj

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )
        assert result == {
            "organization": organization,
            "roles": set(),
            "invitations": set(),
            "form": form_obj,
            "organizations_with_sole_owner": [],
        }

    @freeze_time(datetime.datetime.now(datetime.UTC))
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_post_new_organization_role(
        self,
        db_request,
        orgtype,
        organization_service,
        user_service,
        token_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar", orgtype=orgtype)
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_2,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"username": new_user.username, "role_name": "Owner"}
        )
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        result = org_views.manage_organization_roles(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == new_user)
            .filter(OrganizationInvitation.organization == organization)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)
        assert send_organization_member_invited_email.calls == [
            pretend.call(
                db_request,
                {owner_1, owner_2},
                user=new_user,
                desired_role=db_request.POST["role_name"],
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": db_request.POST["role_name"],
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]
        assert send_organization_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=db_request.POST["role_name"],
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": db_request.POST["role_name"],
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]

    def test_post_duplicate_organization_role(
        self, db_request, organization_service, user_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data=role.role_name),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' already has Owner role for organization", queue="error"
            )
        ]

        # No additional roles are created
        assert role == db_request.db.query(OrganizationRole).one()

        assert isinstance(result, HTTPSeeOther)

    @pytest.mark.parametrize("with_email", [True, False])
    def test_post_unverified_email(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        with_email,
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        if with_email:
            EmailFactory.create(user=user, verified=False, primary=True)

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' does not have a verified primary email address "
                "and cannot be added as a Owner for organization",
                queue="error",
            )
        ]

        # No additional roles are created
        assert db_request.db.query(OrganizationRole).all() == []

        assert isinstance(result, HTTPSeeOther)

    def test_cannot_reinvite_organization_role(
        self, db_request, organization_service, user_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_2,
            role_name=OrganizationRoleType.Owner,
        )
        token_service = db_request.find_service(ITokenService, name="email")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
            invite_status=OrganizationInvitationStatus.Pending,
            token=token_service.dumps({"action": "email-organization-role-verify"}),
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'new_user' already has an active invite. Please try again later.",
                queue="error",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    @freeze_time(datetime.datetime.now(datetime.UTC))
    def test_reinvite_organization_role_after_expiration(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            user=owner_2,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )
        token_service = db_request.find_service(ITokenService, name="email")
        OrganizationInvitationFactory.create(
            user=new_user,
            organization=organization,
            invite_status=OrganizationInvitationStatus.Expired,
            token=token_service.dumps({}),
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == new_user)
            .filter(OrganizationInvitation.organization == organization)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)
        assert send_organization_member_invited_email.calls == [
            pretend.call(
                db_request,
                {owner_1, owner_2},
                user=new_user,
                desired_role=form_obj.role_name.data.value,
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": form_obj.role_name.data.value,
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]
        assert send_organization_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=form_obj.role_name.data.value,
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": form_obj.role_name.data.value,
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]


class TestResendOrganizationInvitations:
    @freeze_time(datetime.datetime.now(datetime.UTC))
    def test_resend_invitation(
        self, db_request, token_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        EmailFactory.create(user=user, verified=True, primary=True)
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            invite_status=OrganizationInvitationStatus.Expired,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.raiser(TokenExpired)
        token_service.unsafe_load_payload = pretend.call_recorder(
            lambda data: {
                "action": "email-organization-role-verify",
                "desired_role": "Manager",
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        result = org_views.resend_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .filter(
                OrganizationInvitation.invite_status
                == OrganizationInvitationStatus.Pending
            )
            .one()
        )
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{user.username}'", queue="success")
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

        assert send_organization_member_invited_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                desired_role="Manager",
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": "Manager",
                        "user_id": user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]
        assert send_organization_role_verification_email.calls == [
            pretend.call(
                db_request,
                user,
                desired_role="Manager",
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": "Manager",
                        "user_id": user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]

    def test_resend_invitation_fails_corrupt_token(
        self, db_request, token_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            invite_status=OrganizationInvitationStatus.Expired,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.raiser(TokenExpired)
        token_service.unsafe_load_payload = pretend.call_recorder(lambda data: None)

        result = org_views.resend_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .filter(
                OrganizationInvitation.invite_status
                == OrganizationInvitationStatus.Pending
            )
            .one_or_none()
        ) is None
        assert db_request.session.flash.calls == [
            pretend.call("Organization invitation could not be re-sent.", queue="error")
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

    def test_resend_invitation_fails_missing_invitation(
        self, db_request, token_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = org_views.resend_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .filter(
                OrganizationInvitation.invite_status
                == OrganizationInvitationStatus.Pending
            )
            .one_or_none()
        ) is None
        assert db_request.session.flash.calls == [
            pretend.call("Could not find organization invitation.", queue="error")
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"


class TestRevokeOrganizationInvitation:
    def test_revoke_invitation(
        self, db_request, token_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(
            lambda data: {
                "action": "email-organization-role-verify",
                "desired_role": "Manager",
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        organization_member_invite_canceled_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invite_canceled_email",
            organization_member_invite_canceled_email,
        )
        canceled_as_invited_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            org_views,
            "send_canceled_as_invited_organization_member_email",
            canceled_as_invited_organization_member_email,
        )

        result = org_views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert organization_member_invite_canceled_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                organization_name=organization.name,
            )
        ]
        assert canceled_as_invited_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                organization_name=organization.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation revoked from '{user.username}'.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

    def test_invitation_does_not_exist(
        self, db_request, token_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(lambda data: None)

        result = org_views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert db_request.session.flash.calls == [
            pretend.call("Could not find organization invitation.", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

    def test_token_expired(self, db_request, token_service, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/roles"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(pretend.raiser(TokenExpired))

        result = org_views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert db_request.session.flash.calls == [
            pretend.call("Expired invitation for 'testuser' deleted.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/roles"


class TestChangeOrganizationRole:
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_change_role(self, db_request, orgtype, enable_organizations, monkeypatch):
        organization = OrganizationFactory.create(name="foobar", orgtype=orgtype)
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        new_role_name = "Manager"

        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id, "role_name": new_role_name})
        db_request.user = user_2
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_organization_member_role_changed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_role_changed_email",
            send_organization_member_role_changed_email,
        )
        send_role_changed_as_organization_member_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            org_views,
            "send_role_changed_as_organization_member_email",
            send_role_changed_as_organization_member_email,
        )

        result = org_views.change_organization_role(organization, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert send_organization_member_role_changed_email.calls == [
            pretend.call(
                db_request,
                set(),
                user=user,
                submitter=user_2,
                organization_name="foobar",
                role=new_role_name,
            )
        ]
        assert send_role_changed_as_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=user_2,
                organization_name="foobar",
                role=new_role_name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Changed role", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_organization_role_invalid_role_name(
        self, db_request, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": str(uuid.uuid4()), "role_name": "Invalid Role Name"}
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.change_organization_role(organization, db_request)

        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_missing_organization_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": missing_role_id, "role_name": "Owner"})
        db_request.user = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.change_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_organization_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            user=user, organization=organization, role_name="Owner"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id, "role_name": "Manager"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.change_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteOrganizationRoles:
    def test_delete_role(self, db_request, enable_organizations, monkeypatch):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = user_2
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_organization_member_removed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_removed_email",
            send_organization_member_removed_email,
        )
        send_removed_as_organization_member_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            org_views,
            "send_removed_as_organization_member_email",
            send_removed_as_organization_member_email,
        )

        result = org_views.delete_organization_role(organization, db_request)

        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert db_request.db.query(OrganizationRole).all() == []
        assert send_organization_member_removed_email.calls == [
            pretend.call(
                db_request,
                set(),
                user=user,
                submitter=user_2,
                organization_name="foobar",
            )
        ]
        assert send_removed_as_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=user_2,
                organization_name="foobar",
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed from organization", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_missing_role(self, db_request, enable_organizations, monkeypatch):
        organization = OrganizationFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [],
                "organizations_owned": [organization],
                "organizations_billing": [],
                "organizations_with_sole_owner": [],
            }
        )
        monkeypatch.setattr(org_views, "user_organizations", user_organizations)

        db_request.method = "POST"
        db_request.user = pretend.stub()
        db_request.POST = MultiDict({"role_id": missing_role_id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.delete_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_other_role_as_nonowner(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.user = user_2
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.has_permission = pretend.call_recorder(lambda *a, **kw: False)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.delete_organization_role(organization, db_request)

        assert db_request.has_permission.calls == [
            pretend.call(Permissions.OrganizationsManage)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Cannot remove other people from the organization", queue="error"
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.delete_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Sole Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_non_owner_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        some_other_user = UserFactory.create(username="someotheruser")
        some_other_organization = OrganizationFactory.create(
            name="someotherorganization"
        )

        db_request.method = "POST"
        db_request.user = some_other_user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = org_views.delete_organization_role(some_other_organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestManageOrganizationHistory:
    def test_get(self, db_request, user_service):
        organization = OrganizationFactory.create()
        older_event = OrganizationEventFactory.create(
            source=organization,
            tag="fake:event",
            time=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_event = OrganizationEventFactory.create(
            source=organization,
            tag="fake:event",
            time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        )

        assert org_views.manage_organization_history(organization, db_request) == {
            "events": [newer_event, older_event],
            "get_user": user_service.get_user,
            "organization": organization,
        }

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        events_query = pretend.stub()
        db_request.events_query = pretend.stub(
            events_query=lambda *a, **kw: events_query
        )

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        organization = OrganizationFactory.create()
        with pytest.raises(HTTPBadRequest):
            org_views.manage_organization_history(organization, db_request)

        assert page_cls.calls == []

    def test_first_page(self, db_request, user_service):
        page_number = 1
        params = MultiDict({"page": page_number})
        db_request.params = params

        organization = OrganizationFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        OrganizationEventFactory.create_batch(
            total_items, source=organization, tag="fake:event"
        )
        events_query = (
            db_request.db.query(Organization.Event)
            .join(Organization.Event.source)
            .filter(Organization.Event.source_id == organization.id)
            .order_by(Organization.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert org_views.manage_organization_history(organization, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "organization": organization,
        }

    def test_last_page(self, db_request, user_service):
        page_number = 2
        params = MultiDict({"page": page_number})
        db_request.params = params

        organization = OrganizationFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        OrganizationEventFactory.create_batch(
            total_items, source=organization, tag="fake:event"
        )
        events_query = (
            db_request.db.query(Organization.Event)
            .join(Organization.Event.source)
            .filter(Organization.Event.source_id == organization.id)
            .order_by(Organization.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert org_views.manage_organization_history(organization, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "organization": organization,
        }

    def test_raises_404_with_out_of_range_page(self, db_request):
        page_number = 3
        params = MultiDict({"page": page_number})
        db_request.params = params

        organization = OrganizationFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        OrganizationEventFactory.create_batch(
            total_items, source=organization, tag="fake:event"
        )

        with pytest.raises(HTTPNotFound):
            assert org_views.manage_organization_history(organization, db_request)
