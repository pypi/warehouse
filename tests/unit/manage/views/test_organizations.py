# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import re
import uuid

import pretend
import pytest

from freezegun import freeze_time
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPTooManyRequests,
)
from sqlalchemy import select, update
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.oidc import PendingGitHubPublisherFactory
from tests.common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationApplicationObservationFactory,
    OrganizationEventFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationOIDCIssuerFactory,
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
from warehouse.accounts import ITokenService
from warehouse.accounts.models import TermsOfServiceEngagement
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.events.tags import EventTag
from warehouse.manage import views
from warehouse.manage.views import organizations as org_views, view_helpers
from warehouse.oidc.models import PendingGitHubPublisher, PendingGitLabPublisher
from warehouse.organizations.models import (
    OIDCIssuerType,
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationTermsOfServiceEngagement,
    OrganizationType,
    Team,
)
from warehouse.packaging import IProjectService, Project, Role
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter, RateLimiter
from warehouse.subscriptions.services import StripeBillingService
from warehouse.utils.paginate import paginate_url_factory


class TestManageOrganizationApplication:
    def test_manage_organization_application(self, db_request):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Submitted
        )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        assert view.manage_organization_application() == {
            "organization_application": _organization_application,
            "information_requests": [],
            "response_forms": {},
        }
        assert (
            _organization_application.status == OrganizationApplicationStatus.Submitted
        )

    def test_manage_organization_application_response_with_info_requests(
        self, db_request, organization_service, monkeypatch
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        with freeze_time() as frozen_datetime:
            _request_for_more_info0 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                created=dt.datetime.now(dt.UTC),
            )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application()

        assert (
            _organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert _response["organization_application"] == _organization_application
        assert _response["information_requests"] == [
            _request_for_more_info1,
            _request_for_more_info0,
        ]
        assert len(_response["response_forms"]) == 2
        assert _request_for_more_info0.id in _response["response_forms"]
        assert _request_for_more_info1.id in _response["response_forms"]

    def test_manage_organization_application_response_with_info_requests_and_responses(
        self, db_request, organization_service, monkeypatch
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        with freeze_time() as frozen_datetime:
            _request_for_more_info0 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                additional={
                    "response": "you got it",
                    "response_time": "2025-03-14T15:40:36.485495+00:00",
                },
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                created=dt.datetime.now(dt.UTC),
            )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application()

        assert (
            _organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert _response["organization_application"] == _organization_application
        assert _response["information_requests"] == [
            _request_for_more_info1,
            _request_for_more_info0,
        ]
        assert len(_response["response_forms"]) == 1
        assert _request_for_more_info1.id in _response["response_forms"]

    def test_manage_organization_application_response_with_all_responded(
        self, db_request, organization_service
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.Submitted
        )

        with freeze_time() as frozen_datetime:
            _request_for_more_info0 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                additional={
                    "response": "you got it",
                    "response_time": "2025-03-14T15:40:36.485495+00:00",
                },
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                additional={
                    "response": "you got it",
                    "response_time": "2025-03-14T15:40:36.485495+00:00",
                },
                created=dt.datetime.now(dt.UTC),
            )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application()

        assert (
            _organization_application.status == OrganizationApplicationStatus.Submitted
        )
        assert _response["organization_application"] == _organization_application
        assert _response["information_requests"] == [
            _request_for_more_info1,
            _request_for_more_info0,
        ]
        assert len(_response["response_forms"]) == 0

    def test_manage_organization_application_submit_empty(
        self, db_request, organization_service
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        with freeze_time() as frozen_datetime:
            _request_for_more_info0 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                additional={
                    "response": "you got it",
                    "response_time": "2025-03-14T15:40:36.485495+00:00",
                },
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                created=dt.datetime.now(dt.UTC),
            )

        db_request.POST = MultiDict({})

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application_submit()

        assert (
            _organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert _response["organization_application"] == _organization_application
        assert _response["information_requests"] == [
            _request_for_more_info1,
            _request_for_more_info0,
        ]
        assert len(_response["response_forms"]) == 1
        assert _request_for_more_info1.id in _response["response_forms"]

    def test_manage_organization_application_submit_response(
        self, db_request, organization_service
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        with freeze_time() as frozen_datetime:
            OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                additional={
                    "response": "you got it",
                    "response_time": "2025-03-14T15:40:36.485495+00:00",
                },
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                created=dt.datetime.now(dt.UTC),
            )

        db_request.POST = MultiDict(
            {
                "response_form-id": _request_for_more_info1.id.__str__(),
                "response": "This is my response",
            }
        )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application_submit()

        assert (
            _organization_application.status == OrganizationApplicationStatus.Submitted
        )
        assert isinstance(_response, HTTPSeeOther)
        assert _request_for_more_info1.additional["response"] == "This is my response"

    def test_manage_organization_application_submit_response_correct_request(
        self, db_request, organization_service
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        with freeze_time() as frozen_datetime:
            OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we need more information"},
                created=dt.datetime.now(dt.UTC),
            )
            frozen_datetime.tick(1.0)
            _request_for_more_info1 = OrganizationApplicationObservationFactory(
                related=_organization_application,
                payload={"message": "we still need more information"},
                created=dt.datetime.now(dt.UTC),
            )

        db_request.POST = MultiDict(
            {
                "response_form-id": _request_for_more_info1.id.__str__(),
                "response": "This is my response",
            }
        )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )
        _response = view.manage_organization_application_submit()

        assert (
            _organization_application.status
            == OrganizationApplicationStatus.MoreInformationNeeded
        )
        assert isinstance(_response, HTTPSeeOther)
        assert _request_for_more_info1.additional["response"] == "This is my response"

    def test_manage_organization_application_submit_invalid_request_id(
        self, db_request, organization_service
    ):
        _organization_application = OrganizationApplicationFactory.create(
            status=OrganizationApplicationStatus.MoreInformationNeeded
        )

        OrganizationApplicationObservationFactory(
            related=_organization_application,
            payload={"message": "we need more information"},
            created=dt.datetime.now(dt.UTC),
        )

        # Use an invalid UUID that doesn't match the actual observation
        invalid_id = str(uuid.uuid4())

        db_request.POST = MultiDict(
            {
                "response_form-id": invalid_id,
                "response": "This is my response",
            }
        )

        view = org_views.ManageOrganizationApplicationViews(
            _organization_application, db_request
        )

        with pytest.raises(
            HTTPBadRequest, match=re.escape("Invalid information request.")
        ):
            view.manage_organization_application_submit()

    @pytest.mark.parametrize(
        ("status", "confirm", "withdrawn"),
        [
            (OrganizationApplicationStatus.Submitted, " example ", True),
            (OrganizationApplicationStatus.Submitted, "wrong", False),
            (OrganizationApplicationStatus.Declined, "example", False),
            (OrganizationApplicationStatus.Withdrawn, "example", False),
        ],
    )
    def test_withdraw_organization_application(
        self, db_request, metrics, mocker, status, confirm, withdrawn
    ):
        app = OrganizationApplicationFactory.create(
            name="example",
            status=status,
            orgtype=OrganizationType.Company,
            submitted=dt.datetime(2026, 1, 1),
        )
        db_request.POST = MultiDict({"confirm_organization_application_name": confirm})
        db_request.route_path = lambda *a, **kw: "/manage/organizations/"

        view = org_views.ManageOrganizationApplicationViews(app, db_request)
        with freeze_time("2026-01-02"):
            assert isinstance(view.withdraw_organization_application(), HTTPSeeOther)
        db_request.db.flush()
        db_request.db.expire(app)

        assert app.status == (
            OrganizationApplicationStatus.Withdrawn if withdrawn else status
        )
        tags = ["status:submitted", "orgtype:Company"]
        assert metrics.increment.call_args_list == (
            [mocker.call("warehouse.organizations.application.withdrawn", tags=tags)]
            if withdrawn
            else []
        )
        assert metrics.distribution.call_args_list == (
            [
                mocker.call(
                    "warehouse.organizations.application.withdrawn.age_seconds",
                    86400.0,
                    tags=tags,
                )
            ]
            if withdrawn
            else []
        )

    def test_withdraw_organization_application_decided_concurrently(
        self, db_request, metrics
    ):
        app = OrganizationApplicationFactory.create(
            name="example", status=OrganizationApplicationStatus.Submitted
        )
        # An admin decides the request after this request loaded it.
        db_request.db.execute(
            update(OrganizationApplication)
            .where(OrganizationApplication.id == app.id)
            .values(status=OrganizationApplicationStatus.Approved)
            .execution_options(synchronize_session=False)
        )
        assert app.status == OrganizationApplicationStatus.Submitted
        db_request.POST = MultiDict(
            {"confirm_organization_application_name": "example"}
        )
        db_request.route_path = lambda *a, **kw: "/manage/organizations/"

        view = org_views.ManageOrganizationApplicationViews(app, db_request)
        assert isinstance(view.withdraw_organization_application(), HTTPSeeOther)
        db_request.db.flush()
        db_request.db.expire(app)

        assert app.status == OrganizationApplicationStatus.Approved
        assert metrics.increment.call_args_list == []


class TestManageOrganizations:
    @pytest.fixture
    def org_request(self, db_request):
        db_request.registry.settings[
            "warehouse.organizations.max_undecided_organization_applications"
        ] = 3
        db_request.user = UserFactory.create()
        return db_request

    @pytest.fixture
    def application_post(self):
        return MultiDict(
            {
                "name": "my_organization_name",
                "display_name": "My Organization",
                "link_url": "https://example.com/",
                "description": "An organization",
                "orgtype": "Community",
                "membership_size": "1",
                "usage": "We plan to publish a few packages under one organization.",
            }
        )

    def test_default_response(self, org_request):
        organization = OrganizationFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=org_request.user,
            role_name=OrganizationRoleType.Owner,
        )
        submitted = OrganizationApplicationFactory.create(submitted_by=org_request.user)
        OrganizationApplicationFactory.create_batch(
            2,
            submitted_by=org_request.user,
            status=OrganizationApplicationStatus.Withdrawn,
        )
        org_request.registry.settings[
            "warehouse.organizations.max_undecided_organization_applications"
        ] = 2

        view = org_views.ManageOrganizationsViews(org_request)
        response = view.default_response

        form = response.pop("create_organization_application_form")
        assert isinstance(form, org_views.CreateOrganizationApplicationForm)
        assert response == {
            "organization_applications": [submitted],
            "organization_invites": [],
            "organizations": [organization],
            "organizations_managed": [],
            "organizations_owned": [organization.name],
            "organizations_billing": [],
        }

    def test_manage_organizations(self, org_request, mocker):
        default_response = mocker.patch.object(
            org_views.ManageOrganizationsViews,
            "default_response",
            new_callable=mocker.PropertyMock,
        )

        view = org_views.ManageOrganizationsViews(org_request)

        assert view.manage_organizations() is default_response.return_value

    @pytest.mark.parametrize("orgtype", ["Community", "Company"])
    def test_create_organization_application(
        self, org_request, application_post, orgtype, mocker
    ):
        application_post["orgtype"] = orgtype
        org_request.POST = application_post
        mocker.spy(org_request.session, "flash")
        send_email = mocker.patch.object(
            org_views, "send_new_organization_requested_email", autospec=True
        )

        view = org_views.ManageOrganizationsViews(org_request)
        result = view.create_organization_application()

        application = org_request.db.scalars(select(OrganizationApplication)).one()
        assert application.name == "my_organization_name"
        assert application.display_name == "My Organization"
        assert application.orgtype == OrganizationType(orgtype)
        assert application.link_url == "https://example.com/"
        assert application.description == "An organization"
        assert application.submitted_by == org_request.user
        assert application.membership_size == "1"
        assert application.usage == (
            "We plan to publish a few packages under one organization."
        )
        # Submitting an application grants no organization role.
        assert org_request.db.scalars(select(OrganizationRole)).all() == []
        send_email.assert_called_once_with(
            org_request, org_request.user, organization_name="my_organization_name"
        )
        org_request.session.flash.assert_called_once_with(
            "Request for new organization submitted", queue="success"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == org_request.path

    def test_create_organization_application_validation_fails(
        self, org_request, mocker
    ):
        org_request.POST = MultiDict({})
        send_email = mocker.patch.object(
            org_views, "send_new_organization_requested_email", autospec=True
        )

        view = org_views.ManageOrganizationsViews(org_request)
        result = view.create_organization_application()

        form = result["create_organization_application_form"]
        assert isinstance(form, org_views.CreateOrganizationApplicationForm)
        assert form.errors
        assert org_request.db.scalars(select(OrganizationApplication)).all() == []
        send_email.assert_not_called()

    def test_create_organization_application_max_undecided(
        self, pyramid_config, org_request, application_post, mocker
    ):
        OrganizationApplicationFactory.create_batch(
            3,
            submitted_by=org_request.user,
            status=OrganizationApplicationStatus.Submitted,
        )
        org_request.POST = application_post
        send_email = mocker.patch.object(
            org_views, "send_new_organization_requested_email", autospec=True
        )

        view = org_views.ManageOrganizationsViews(org_request)
        result = view.create_organization_application()

        form = result["create_organization_application_form"]
        assert [str(error) for error in form.form_errors] == [
            (
                "You have already submitted the maximum number of "
                "Organization requests (3)."
            )
        ]
        assert len(org_request.user.organization_applications) == 3
        send_email.assert_not_called()


class TestManageOrganizationSettings:
    @staticmethod
    def _organization_row(db_request, organization):
        """Look up the organization through a query, which flushes first and so
        sees a pending delete."""
        return db_request.db.scalars(
            select(Organization).filter_by(id=organization.id)
        ).one_or_none()

    @pytest.fixture
    def organization(self, pyramid_user):
        organization = OrganizationFactory.create(name="foobar")
        OrganizationRoleFactory.create(
            organization=organization,
            user=pyramid_user,
            role_name=OrganizationRoleType.Owner,
        )
        return organization

    def test_manage_organization(
        self, db_request, pyramid_user, organization, organization_service
    ):
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.manage_organization()

        assert view.request == db_request
        assert view.organization_service == organization_service
        save_organization_form = result.pop("save_organization_form")
        assert isinstance(save_organization_form, org_views.SaveOrganizationForm)
        assert save_organization_form.data == {
            "display_name": organization.display_name,
            "link_url": organization.link_url,
            "description": organization.description,
            "orgtype": organization.orgtype,
        }
        save_organization_name_form = result.pop("save_organization_name_form")
        assert isinstance(
            save_organization_name_form, org_views.SaveOrganizationNameForm
        )
        assert save_organization_name_form.user == pyramid_user
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
        }

    @pytest.mark.parametrize(
        ("orgtype", "has_customer"),
        [(orgtype, True) for orgtype in list(OrganizationType)]
        + [(orgtype, False) for orgtype in list(OrganizationType)],
    )
    def test_save_organization(
        self,
        db_request,
        pyramid_user,
        organization,
        orgtype,
        has_customer,
        billing_service,
        mocker,
    ):
        organization.orgtype = orgtype
        previous_display_name = organization.display_name
        customer = StripeCustomerFactory.create()
        if has_customer:
            OrganizationStripeCustomerFactory.create(
                organization=organization, customer=customer
            )
        db_request.POST = MultiDict(
            {
                "display_name": "New Display Name",
                "link_url": organization.link_url,
                "description": organization.description,
                "orgtype": organization.orgtype.value,
            }
        )
        db_request.registry.settings["site.name"] = "PiePeaEye"
        update_customer = mocker.patch.object(
            billing_service, "update_customer", autospec=True
        )
        send_email = mocker.patch.object(
            org_views, "send_organization_updated_email", autospec=True
        )
        mocker.spy(db_request.session, "flash")

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert isinstance(result, HTTPSeeOther)
        assert organization.display_name == "New Display Name"
        if has_customer:
            update_customer.assert_called_once_with(
                customer.customer_id,
                f"PiePeaEye Organization - New Display Name ({organization.name})",
                organization.description,
            )
        else:
            update_customer.assert_not_called()
        send_email.assert_called_once_with(
            db_request,
            {pyramid_user},
            organization_name=organization.name,
            organization_display_name="New Display Name",
            organization_link_url=organization.link_url,
            organization_description=organization.description,
            organization_orgtype=orgtype,
            previous_organization_display_name=previous_display_name,
            previous_organization_link_url=organization.link_url,
            previous_organization_description=organization.description,
            previous_organization_orgtype=orgtype,
        )
        db_request.session.flash.assert_called_once_with(
            "Organization details updated", queue="success"
        )

    def test_save_organization_company_cannot_become_community(
        self, db_request, organization, billing_service, mocker
    ):
        """A Company organization keeps its type even if Community is posted."""
        organization.orgtype = OrganizationType.Company
        db_request.POST = MultiDict(
            {
                "display_name": organization.display_name,
                "link_url": organization.link_url,
                "description": organization.description,
                "orgtype": OrganizationType.Community.value,
            }
        )
        db_request.registry.settings["site.name"] = "PiePeaEye"
        send_email = mocker.patch.object(
            org_views, "send_organization_updated_email", autospec=True
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert isinstance(result, HTTPSeeOther)
        assert organization.orgtype == OrganizationType.Company
        assert (
            send_email.call_args.kwargs["organization_orgtype"]
            == OrganizationType.Company
        )

    def test_save_organization_validation_fails(self, db_request, organization, mocker):
        previous_display_name = organization.display_name
        db_request.POST = MultiDict(
            {
                "display_name": "",
                "link_url": organization.link_url,
                "description": organization.description,
                "orgtype": organization.orgtype.value,
            }
        )
        send_email = mocker.patch.object(
            org_views, "send_organization_updated_email", autospec=True
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        form = result.pop("save_organization_form")
        assert form.errors == {"display_name": ["Specify your organization name"]}
        assert isinstance(
            result.pop("save_organization_name_form"),
            org_views.SaveOrganizationNameForm,
        )
        assert result == {"organization": organization, "active_projects": []}
        assert organization.display_name == previous_display_name
        send_email.assert_not_called()

    def test_save_organization_name_wrong_confirm(
        self, db_request, organization, mocker
    ):
        db_request.POST = MultiDict(
            {
                "confirm_current_organization_name": organization.name.upper(),
                "name": "FooBar",
            }
        )
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )
        mocker.spy(db_request.session, "flash")

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        with pytest.raises(HTTPSeeOther):
            view.save_organization_name()

        db_request.session.flash.assert_called_once_with(
            "Could not rename organization - 'FOOBAR' is not the same as 'foobar'",
            queue="error",
        )

    def test_disable_save_organization_name(self, db_request, organization, mocker):
        db_request.POST = MultiDict(
            {
                "confirm_current_organization_name": organization.name,
                "name": "FooBar",
            }
        )
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value=f"/manage/organization/{organization.normalized_name}/settings/",
        )
        mocker.spy(db_request.session, "flash")

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization_name()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == (
            f"/manage/organization/{organization.normalized_name}/settings/"
        )
        db_request.route_path.assert_called_once_with(
            "manage.organization.settings",
            organization_name=organization.normalized_name,
        )
        db_request.session.flash.assert_called_once_with(
            "Organization names cannot be changed", queue="error"
        )

    # When support for renaming orgs is re-introduced
    # def test_save_organization_name(
    #    self, db_request, pyramid_user, organization, mocker
    # ):
    #    db_request.POST = MultiDict(
    #        {
    #            "confirm_current_organization_name": organization.name,
    #            "name": "FooBar",
    #        }
    #    )
    #    mocker.patch.object(
    #        db_request,
    #        "route_path",
    #        autospec=True,
    #        return_value="/manage/organization/foobar/settings/",
    #    )
    #    send_email = mocker.patch.object(
    #        org_views, "send_organization_renamed_email", autospec=True
    #    )

    #    view = org_views.ManageOrganizationSettingsViews(organization, db_request)
    #    result = view.save_organization_name()

    #    assert isinstance(result, HTTPSeeOther)
    #    assert result.headers["Location"] == (
    #        "/manage/organization/foobar/settings/#modal-close"
    #    )
    #    assert organization.name == "FooBar"
    #    send_email.assert_called_once_with(
    #        db_request,
    #        {pyramid_user},
    #        organization_name="FooBar",
    #        previous_organization_name="foobar",
    #    )

    # def test_save_organization_name_validation_fails(
    #    self, db_request, organization
    # ):
    #    OrganizationFactory.create(name="FooBar2")
    #    db_request.POST = MultiDict(
    #        {
    #            "confirm_current_organization_name": organization.name,
    #            "name": "FooBar2",
    #        }
    #    )

    #    view = org_views.ManageOrganizationSettingsViews(organization, db_request)
    #    result = view.save_organization_name()

    #    assert result["save_organization_name_form"].errors
    #    assert organization.name == "foobar"

    def test_delete_organization(self, db_request, pyramid_user, organization, mocker):
        db_request.POST = MultiDict({"confirm_organization_name": organization.name})
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/manage/organizations/",
        )
        send_email = mocker.patch.object(
            org_views, "send_organization_deleted_email", autospec=True
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        assert self._organization_row(db_request, organization) is None
        send_email.assert_called_once_with(
            db_request, {pyramid_user}, organization_name="foobar"
        )
        db_request.route_path.assert_called_once_with("manage.organizations")

    def test_delete_organization_with_active_projects(
        self, db_request, organization, mocker
    ):
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        db_request.POST = MultiDict({"confirm_organization_name": organization.name})
        mocker.patch.object(db_request, "route_path", autospec=True)
        mocker.spy(db_request.session, "flash")
        send_email = mocker.patch.object(
            org_views, "send_organization_deleted_email", autospec=True
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(
            result.pop("save_organization_form"), org_views.SaveOrganizationForm
        )
        assert isinstance(
            result.pop("save_organization_name_form"),
            org_views.SaveOrganizationNameForm,
        )
        assert result == {
            "organization": organization,
            "active_projects": organization.projects,
        }
        assert self._organization_row(db_request, organization) is organization
        db_request.session.flash.assert_called_once_with(
            "Cannot delete organization with active project ownerships",
            queue="error",
        )
        send_email.assert_not_called()
        db_request.route_path.assert_not_called()

    @pytest.mark.parametrize(
        ("subscription_status", "should_cancel"),
        [
            ("active", True),
            ("past_due", True),
            ("canceled", False),
            ("incomplete_expired", False),
        ],
    )
    def test_delete_organization_with_subscriptions(
        self,
        db_request,
        pyramid_user,
        organization,
        billing_service,
        mocker,
        subscription_status,
        should_cancel,
    ):
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(
            customer=stripe_customer, status=subscription_status
        )
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        cancel_subscription = mocker.patch.object(
            billing_service, "cancel_subscription", autospec=True
        )
        db_request.POST = MultiDict({"confirm_organization_name": organization.name})
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/manage/organizations/",
        )
        send_email = mocker.patch.object(
            org_views, "send_organization_deleted_email", autospec=True
        )

        view = org_views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        if should_cancel:
            cancel_subscription.assert_called_once_with(subscription.subscription_id)
        else:
            cancel_subscription.assert_not_called()
        assert self._organization_row(db_request, organization) is None
        send_email.assert_called_once_with(
            db_request, {pyramid_user}, organization_name="foobar"
        )
        db_request.route_path.assert_called_once_with("manage.organizations")


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

    @pytest.fixture
    def stripe_billing_service(self, mocker):
        """A billing service that is not the local MockStripeBillingService."""
        return mocker.create_autospec(StripeBillingService, instance=True)

    def test_customer_id(self, db_request, organization):
        view = org_views.ManageOrganizationBillingViews(organization, db_request)
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

    @pytest.mark.parametrize(
        ("next_param", "expected_url", "uses_default"),
        [
            # No next parameter - should fall back to default
            (None, "https://pypi.org/manage/organizations/", True),
            # Unsafe external URL - should fall back to default
            (
                "https://evil.com/phishing",
                "https://pypi.org/manage/organizations/",
                True,
            ),
            # Safe internal URL - should use the provided URL
            ("/manage/projects/", "https://pypi.org/manage/projects/", False),
        ],
    )
    def test_return_url(
        self, db_request, organization, next_param, expected_url, uses_default, mocker
    ):
        db_request.GET = {} if next_param is None else {"next": next_param}
        db_request.host = "pypi.org"
        db_request.application_url = "https://pypi.org"
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/manage/organizations/",
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        return_url = view.return_url

        if uses_default:
            db_request.route_path.assert_called_once_with("manage.organizations")
        else:
            db_request.route_path.assert_not_called()
        assert return_url == expected_url

    def test_activate_subscription(self, db_request, organization, mocker):
        db_request.POST = MultiDict()

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.activate_subscription()

        assert result == {"organization": organization, "form": mocker.ANY}
        assert isinstance(result["form"], org_views.OrganizationActivateBillingForm)

    def test_post_activate_subscription_valid(self, db_request, organization, mocker):
        db_request.method = "POST"
        db_request.POST = MultiDict({"terms_of_service_agreement": "1"})
        db_request.registry.settings["terms.revision"] = "initial"
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="mock-billing-url"
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.activate_subscription()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-billing-url"
        db_request.route_path.assert_called_once_with(
            "manage.organization.subscription",
            organization_name=organization.normalized_name,
        )
        engagement = db_request.db.scalars(
            select(OrganizationTermsOfServiceEngagement).filter_by(
                organization_id=organization.id
            )
        ).one()
        assert engagement.engagement == TermsOfServiceEngagement.Agreed
        assert engagement.revision == "initial"

    def test_post_activate_subscription_invalid(self, db_request, organization):
        db_request.method = "POST"
        db_request.POST = MultiDict()

        view = org_views.ManageOrganizationBillingViews(organization, db_request)

        result = view.activate_subscription()

        assert result["organization"] == organization
        assert result["form"].terms_of_service_agreement.errors == [
            "Terms of Service must be accepted."
        ]

    @pytest.mark.parametrize(
        "view_method", ["activate_subscription", "create_or_manage_subscription"]
    )
    def test_deactivated_organization_cannot_start_subscription(
        self, db_request, organization_no_customer, mocker, view_method
    ):
        organization_no_customer.is_active = False
        db_request.method = "POST"
        db_request.POST = MultiDict({"terms_of_service_agreement": "1"})
        db_request.route_path = mocker.Mock(return_value="/settings/")
        flash = mocker.spy(db_request.session, "flash")

        view = org_views.ManageOrganizationBillingViews(
            organization_no_customer, db_request
        )
        create_subscription = mocker.patch.object(view, "create_subscription")
        result = getattr(view, view_method)()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/settings/"
        db_request.route_path.assert_called_once_with(
            "manage.organization.settings",
            organization_name=organization_no_customer.normalized_name,
        )
        flash.assert_called_once_with(
            "This organization is deactivated. To reactivate it, email "
            "support+orgs@pypi.org.",
            queue="error",
        )
        create_subscription.assert_not_called()

    def test_org_deactivated_for_no_paid_seat_can_start_subscription(
        self, db_request, organization_no_customer, mocker
    ):
        organization_no_customer.is_active = False
        mocker.patch.object(
            type(organization_no_customer),
            "reactivates_on_payment",
            new_callable=mocker.PropertyMock,
            return_value=True,
        )
        view = org_views.ManageOrganizationBillingViews(
            organization_no_customer, db_request
        )
        create_subscription = mocker.patch.object(view, "create_subscription")

        assert view.create_or_manage_subscription() is create_subscription.return_value

    def test_create_subscription(
        self,
        db_request,
        organization,
        subscription_price,
        stripe_billing_service,
        mocker,
    ):
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="mock-session-url"
        )
        stripe_billing_service.create_checkout_session.return_value = {
            "url": "session-url"
        }

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = stripe_billing_service
        result = view.create_or_manage_subscription()

        stripe_billing_service.create_checkout_session.assert_called_once_with(
            customer_id=organization.customer.customer_id,
            price_ids=[subscription_price.price_id],
            success_url=view.return_url,
            cancel_url=view.return_url,
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_create_subscription_local_mock(
        self,
        db_request,
        billing_service,
        organization,
        subscription_price,
        mocker,
    ):
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="mock-session-url"
        )
        create_checkout_session = mocker.patch.object(
            billing_service,
            "create_checkout_session",
            autospec=True,
            return_value={"url": "session-url"},
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        create_checkout_session.assert_called_once_with(
            customer_id=view.customer_id,
            price_ids=[subscription_price.price_id],
            success_url=view.return_url,
            cancel_url=view.return_url,
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"

    def test_manage_subscription(
        self,
        db_request,
        organization,
        organization_subscription,
        stripe_billing_service,
        mocker,
    ):
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="mock-session-url"
        )
        stripe_billing_service.create_portal_session.return_value = {
            "url": "session-url"
        }

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = stripe_billing_service
        result = view.create_or_manage_subscription()

        stripe_billing_service.create_portal_session.assert_called_once_with(
            customer_id=organization.customer.customer_id,
            return_url=view.return_url,
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_manage_subscription_local_mock(
        self,
        db_request,
        billing_service,
        organization,
        organization_subscription,
        mocker,
    ):
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="mock-session-url"
        )
        create_portal_session = mocker.patch.object(
            billing_service,
            "create_portal_session",
            autospec=True,
            return_value={"url": "session-url"},
        )

        view = org_views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        create_portal_session.assert_called_once_with(
            customer_id=organization.customer.customer_id,
            return_url=view.return_url,
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"


class TestManageOrganizationTeams:
    def test_manage_teams(self, db_request, pyramid_user, organization_service):
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

    def test_create_team(self, db_request, pyramid_user, mocker):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create()]

        db_request.POST = MultiDict({"name": "Team Name"})

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        # Production IP lookups return a loaded object without autoflushing.
        db_request.db.refresh(db_request.ip_address)
        # Authentication also loads the current user before the view runs.
        db_request.db.refresh(db_request.user)

        send_team_created_email = mocker.patch.object(
            org_views, "send_team_created_email", autospec=True
        )

        view = org_views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.create_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        teams = db_request.db.scalars(
            select(Team).filter_by(organization=organization)
        ).all()
        assert len(teams) == 2
        team = next(team for team in teams if team.name == "Team Name")
        assert team.events[0].tag == "team:create"
        assert team.events[0].additional == {
            "organization_name": organization.name,
            "team_name": "Team Name",
            "created_by_user_id": str(db_request.user.id),
        }
        assert organization.events[0].tag == "organization:team:create"
        assert organization.events[0].additional == {
            "organization_name": organization.name,
            "team_name": "Team Name",
            "created_by_user_id": str(db_request.user.id),
        }
        send_team_created_email.assert_called_once_with(
            db_request,
            {db_request.user},
            organization_name=organization.name,
            team_name=team.name,
        )

    def test_create_team_invalid(self, db_request, pyramid_user, organization_service):
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
    @pytest.fixture
    def organization(self, pyramid_user):
        organization = OrganizationFactory.create()
        OrganizationRoleFactory.create(
            organization=organization, user=pyramid_user, role_name="Owner"
        )
        return organization

    def _organization_project_ids(self, db_request, organization):
        return set(
            db_request.db.scalars(
                select(OrganizationProject.project_id).filter_by(
                    organization_id=organization.id
                )
            )
        )

    def test_manage_organization_projects(
        self, db_request, pyramid_user, organization, organization_service
    ):
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        db_request.POST = MultiDict()

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.manage_organization_projects()

        assert view.request == db_request
        assert view.organization_service == organization_service
        form = result.pop("add_organization_project_form")
        assert isinstance(form, org_views.AddOrganizationProjectForm)
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {existing.project.name},
            "projects_sole_owned": {existing.project.name},
        }

    def test_add_organization_project_existing_project(
        self, db_request, pyramid_user, organization, mocker
    ):
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        project = ProjectFactory.create()
        RoleFactory.create(project=project, user=pyramid_user, role_name="Owner")
        db_request.POST = MultiDict(
            {"add_existing_project": "true", "existing_project_name": project.name}
        )
        send_email = mocker.patch.object(
            view_helpers, "send_organization_project_added_email", autospec=True
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert self._organization_project_ids(db_request, organization) == {
            existing.project_id,
            project.id,
        }
        assert (
            db_request.db.scalars(
                select(Role).filter_by(project=project, user=pyramid_user)
            ).all()
            == []
        )
        send_email.assert_called_once_with(
            db_request,
            {pyramid_user},
            organization_name=organization.name,
            project_name=project.name,
            submitter_username=pyramid_user.username,
        )

    def test_add_organization_project_existing_project_no_individual_owner(
        self, db_request, pyramid_user, organization, mocker
    ):
        """
        The form only offers projects the user owns, so skip its validation
        to reach a project with no owner role for the user.
        """
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        project = ProjectFactory.create()
        db_request.POST = MultiDict(
            {"add_existing_project": "true", "existing_project_name": project.name}
        )
        mocker.patch.object(
            org_views.AddOrganizationProjectForm,
            "validate",
            autospec=True,
            return_value=True,
        )
        send_email = mocker.patch.object(
            view_helpers, "send_organization_project_added_email", autospec=True
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert self._organization_project_ids(db_request, organization) == {
            existing.project_id,
            project.id,
        }
        send_email.assert_called_once_with(
            db_request,
            {pyramid_user},
            organization_name=organization.name,
            project_name=project.name,
            submitter_username=pyramid_user.username,
        )

    def test_add_organization_project_existing_project_invalid(
        self, db_request, pyramid_user, organization
    ):
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        project = ProjectFactory.create()
        RoleFactory.create(project=project, user=pyramid_user, role_name="Owner")
        db_request.POST = MultiDict({"add_existing_project": "true"})

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        form = result.pop("add_organization_project_form")
        assert form.existing_project_name.errors == ["Select project"]
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, existing.project.name},
            "projects_sole_owned": {project.name, existing.project.name},
        }
        assert self._organization_project_ids(db_request, organization) == {
            existing.project_id
        }

    def test_add_organization_project_new_project(
        self, db_request, pyramid_user, organization, mocker
    ):
        db_request.user_docs_url = lambda *a, **kw: ""
        db_request.POST = MultiDict(
            {"add_existing_project": "false", "new_project_name": "fakepackage"}
        )
        send_email = mocker.patch.object(
            view_helpers, "send_organization_project_added_email", autospec=True
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
        send_email.assert_called_once_with(
            db_request,
            {pyramid_user},
            organization_name=organization.name,
            project_name="fakepackage",
            submitter_username=pyramid_user.username,
        )

    @pytest.mark.parametrize(
        ("resets_in", "retry_after", "expected_error"),
        [
            (
                dt.timedelta(seconds=600),
                "600",
                (
                    "This organization has created too many new projects recently. "
                    "Try again in 10 minutes."
                ),
            ),
            (
                None,
                None,
                (
                    "This organization has created too many new projects recently. "
                    "Try again later."
                ),
            ),
        ],
        ids=["with-reset-hint", "without-reset-hint"],
    )
    @pytest.mark.parametrize(
        ("limiter_name", "limiter_method"),
        [
            ("project.create.organization", "test"),
            ("project.create.attempt.organization", "hit"),
        ],
        ids=["rejected-before-writing", "rejected-after-writing"],
    )
    def test_add_organization_project_new_project_ratelimited(
        self,
        db_request,
        pyramid_user,
        organization,
        mocker,
        resets_in,
        retry_after,
        expected_error,
        limiter_name,
        limiter_method,
    ):
        """`hit` (on the attempt limiter) rejects after the project is in the
        session, so the view must doom the transaction or pyramid_tm commits
        the refused project."""
        db_request.user_docs_url = lambda *a, **kw: ""
        db_request.POST = MultiDict(
            {"add_existing_project": "false", "new_project_name": "fakepackage"}
        )

        limiter = DummyRateLimiter()
        mocker.patch.object(limiter, limiter_method, return_value=False)
        mocker.patch.object(limiter, "resets_in", return_value=resets_in)
        project_service = db_request.find_service(IProjectService)
        project_service.ratelimiters[limiter_name] = limiter

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        form = result.pop("add_organization_project_form")
        assert form.new_project_name.errors == [expected_error]
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": set(),
            "projects_sole_owned": set(),
        }
        assert db_request.response.status_code == 429
        assert db_request.response.headers.get("Retry-After") == retry_after
        assert db_request.tm.isDoomed()

    @pytest.mark.parametrize(
        ("project_name", "expected"),
        [
            (
                "-invalid-name-",
                (
                    "Start and end with a letter or numeral containing "
                    "only ASCII numeric and '.', '_' and '-'."
                ),
            ),
            (
                "requirements.txt",
                (
                    "The name 'requirements.txt' isn't allowed. See docs-url "
                    "for more information."
                ),
            ),
        ],
    )
    def test_add_organization_project_new_project_invalid(
        self, db_request, pyramid_user, organization, project_name, expected
    ):
        db_request.user_docs_url = lambda *a, **kw: "docs-url"
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        db_request.POST = MultiDict(
            {"add_existing_project": "false", "new_project_name": project_name}
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        form = result.pop("add_organization_project_form")
        assert form.new_project_name.errors == [expected]
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {existing.project.name},
            "projects_sole_owned": {existing.project.name},
        }
        assert self._organization_project_ids(db_request, organization) == {
            existing.project_id
        }

    def test_add_organization_project_new_project_name_conflict(
        self, db_request, pyramid_user, organization
    ):
        existing = OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )
        project = ProjectFactory.create()
        db_request.POST = MultiDict(
            {"add_existing_project": "false", "new_project_name": project.name}
        )

        view = org_views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        form = result.pop("add_organization_project_form")
        assert form.new_project_name.errors == [
            "This project name has already been used. Choose a different project name."
        ]
        assert self._organization_project_ids(db_request, organization) == {
            existing.project_id
        }


class TestManageOrganizationRoles:
    def test_get_manage_organization_roles(self, db_request, pyramid_user):
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
            "is_sole_owner": False,
            "awaiting_initial_billing": False,
            "role_choices": [
                ("", "Select role"),
                ("Member", "Member"),
                ("Manager", "Manager"),
                ("Owner", "Owner"),
            ],
        }

    @freeze_time(dt.datetime.now(dt.UTC))
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_post_new_organization_role(
        self,
        db_request,
        orgtype,
        organization_service,
        user_service,
        token_service,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar", orgtype=orgtype)

        # Company organizations need billing to be in good standing
        if orgtype == OrganizationType.Company:
            OrganizationStripeCustomerFactory.create(organization=organization)
            OrganizationStripeSubscriptionFactory.create(organization=organization)

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
        self, db_request, organization_service, user_service
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
                allow_billing_manager_only=False,
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
                allow_billing_manager_only=False,
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
        self, db_request, organization_service, user_service
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
                allow_billing_manager_only=False,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'new_user' already has an active invite. Please try again later.",
                queue="error",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    @freeze_time(dt.datetime.now(dt.UTC))
    def test_reinvite_organization_role_after_expiration(
        self,
        db_request,
        organization_service,
        user_service,
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
                allow_billing_manager_only=False,
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

    def test_manage_organization_roles_not_in_good_standing(
        self, db_request, monkeypatch
    ):
        organization = OrganizationFactory.create(orgtype="Company")  # No billing
        new_user = UserFactory.create(username="new-user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        form_obj = pretend.stub(
            username=pretend.stub(data="new-user"),
            role_name=pretend.stub(data=OrganizationRoleType.Member),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        db_request.method = "POST"
        db_request.user = owner_user
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert db_request.session.flash.calls == [
            pretend.call(
                "Cannot invite new member. Organization is not in good standing.",
                queue="error",
            )
        ]
        assert isinstance(result, HTTPSeeOther)  # Redirect due to inactive org

    def test_manage_organization_roles_pre_billing_company(
        self, db_request, organization_service, user_service
    ):
        organization = OrganizationFactory.create(
            name="new-company-org", orgtype=OrganizationType.Company
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        db_request.method = "GET"
        db_request.user = owner_user

        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
                allow_billing_manager_only=True,
            )
        ]
        assert result["awaiting_initial_billing"] is True
        assert [choice[0] for choice in result["role_choices"]] == [
            "",
            "Member",
            "Manager",
            "Owner",
            "Billing Manager",
        ]


def _expired_token(token_service, data):
    """Sign data far enough in the past that the token has already expired."""
    with freeze_time(
        dt.datetime.now(dt.UTC) - dt.timedelta(seconds=token_service.max_age + 1)
    ):
        return token_service.dumps(data)


def _invitation(db_request, organization, user, status=None):
    query = (
        db_request.db.query(OrganizationInvitation)
        .filter(OrganizationInvitation.user == user)
        .filter(OrganizationInvitation.organization == organization)
    )
    if status is not None:
        query = query.filter(OrganizationInvitation.invite_status == status)
    return query.one_or_none()


@pytest.fixture
def invite_organization():
    return OrganizationFactory.create(name="foobar")


@pytest.fixture
def invite_owner(invite_organization):
    owner_user = UserFactory.create()
    OrganizationRoleFactory(
        user=owner_user,
        organization=invite_organization,
        role_name=OrganizationRoleType.Owner,
    )
    return owner_user


@pytest.fixture
def invite_request(db_request, invite_owner, mocker):
    """A POST from an organization owner, with the roles route stubbed."""
    db_request.method = "POST"
    db_request.remote_addr = "10.10.10.10"
    db_request.user = invite_owner
    mocker.patch.object(
        db_request,
        "route_path",
        autospec=True,
        return_value="/manage/organization/foobar/people/",
    )
    mocker.spy(db_request.session, "flash")
    return db_request


class TestResendOrganizationInvitations:
    @freeze_time(dt.datetime.now(dt.UTC))
    def test_resend_invitation(
        self, invite_request, invite_organization, invite_owner, token_service, mocker
    ):
        """Resend reads the stored token's payload without checking its expiry,
        so an expired invitation can be sent again."""
        organization = invite_organization
        user = UserFactory.create(username="testuser")
        EmailFactory.create(user=user, verified=True, primary=True)
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            invite_status=OrganizationInvitationStatus.Expired,
            token=_expired_token(
                token_service,
                {
                    "action": "email-organization-role-verify",
                    "desired_role": "Manager",
                    "user_id": user.id,
                    "organization_id": organization.id,
                    "submitter_id": invite_owner.id,
                },
            ),
        )
        member_invited_email = mocker.patch.object(
            org_views, "send_organization_member_invited_email", autospec=True
        )
        role_verification_email = mocker.patch.object(
            org_views, "send_organization_role_verification_email", autospec=True
        )
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.resend_organization_invitation(organization, invite_request)

        assert _invitation(
            invite_request, organization, user, OrganizationInvitationStatus.Pending
        )
        invite_request.session.flash.assert_called_once_with(
            f"Invitation sent to '{user.username}'", queue="success"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"
        invite_request.route_path.assert_called_once_with(
            "manage.organization.roles", organization_name=organization.normalized_name
        )

        email_kwargs = {
            "desired_role": "Manager",
            "initiator_username": invite_owner.username,
            "organization_name": organization.name,
            "email_token": token_service.dumps(
                {
                    "action": "email-organization-role-verify",
                    "desired_role": "Manager",
                    "user_id": user.id,
                    "organization_id": organization.id,
                    "submitter_id": invite_owner.id,
                }
            ),
            "token_age": token_service.max_age,
        }
        member_invited_email.assert_called_once_with(
            invite_request, {invite_owner}, user=user, **email_kwargs
        )
        role_verification_email.assert_called_once_with(
            invite_request, user, **email_kwargs
        )

    def test_resend_invitation_fails_corrupt_token(
        self, invite_request, invite_organization
    ):
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=invite_organization,
            user=user,
            invite_status=OrganizationInvitationStatus.Expired,
            token="not-a-signed-token",
        )
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.resend_organization_invitation(
            invite_organization, invite_request
        )

        assert (
            _invitation(
                invite_request,
                invite_organization,
                user,
                OrganizationInvitationStatus.Pending,
            )
            is None
        )
        invite_request.session.flash.assert_called_once_with(
            "Organization invitation could not be re-sent.", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"

    def test_resend_invitation_fails_missing_invitation(
        self, invite_request, invite_organization
    ):
        user = UserFactory.create(username="testuser")
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.resend_organization_invitation(
            invite_organization, invite_request
        )

        assert _invitation(invite_request, invite_organization, user) is None
        invite_request.session.flash.assert_called_once_with(
            "Could not find organization invitation.", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"


def _assert_revoke_events(request, organization, user, org_event, user_event):
    """An unreadable invitation still records its revocation, without a role."""
    org_event.assert_called_once_with(
        tag=EventTag.Organization.OrganizationRoleRevokeInvite,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "role_name": None,
            "target_user_id": str(user.id),
        },
    )
    user_event.assert_called_once_with(
        tag=EventTag.Account.OrganizationRoleRevokeInvite,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "organization_name": organization.name,
            "role_name": None,
        },
    )


class TestRevokeOrganizationInvitation:
    @pytest.fixture
    def revoke_emails(self, mocker):
        return (
            mocker.patch.object(
                org_views,
                "send_organization_member_invite_canceled_email",
                autospec=True,
            ),
            mocker.patch.object(
                org_views,
                "send_canceled_as_invited_organization_member_email",
                autospec=True,
            ),
        )

    def test_revoke_invitation(
        self,
        invite_request,
        invite_organization,
        invite_owner,
        token_service,
        revoke_emails,
    ):
        organization = invite_organization
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            token=token_service.dumps(
                {
                    "action": "email-organization-role-verify",
                    "desired_role": "Manager",
                    "user_id": user.id,
                    "organization_id": organization.id,
                    "submitter_id": invite_owner.id,
                }
            ),
        )
        invite_request.POST = MultiDict({"user_id": user.id})
        invite_canceled_email, canceled_as_invited_email = revoke_emails

        result = org_views.revoke_organization_invitation(organization, invite_request)

        assert _invitation(invite_request, organization, user) is None
        invite_canceled_email.assert_called_once_with(
            invite_request,
            {invite_owner},
            user=user,
            organization_name=organization.name,
        )
        canceled_as_invited_email.assert_called_once_with(
            invite_request, user, organization_name=organization.name
        )
        invite_request.session.flash.assert_called_once_with(
            f"Invitation revoked from '{user.username}'.", queue="success"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"
        invite_request.route_path.assert_called_once_with(
            "manage.organization.roles", organization_name=organization.normalized_name
        )

    def test_invitation_does_not_exist(self, invite_request, invite_organization):
        user = UserFactory.create(username="testuser")
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.revoke_organization_invitation(
            invite_organization, invite_request
        )

        invite_request.session.flash.assert_called_once_with(
            "Could not find organization invitation.", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"

    def test_token_expired(
        self, invite_request, invite_organization, token_service, revoke_emails, mocker
    ):
        user = UserFactory.create(username="testuser")
        org_event = mocker.patch.object(
            invite_organization, "record_event", autospec=True
        )
        user_event = mocker.patch.object(user, "record_event", autospec=True)
        OrganizationInvitationFactory.create(
            organization=invite_organization,
            user=user,
            token=_expired_token(
                token_service, {"action": "email-organization-role-verify"}
            ),
        )
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.revoke_organization_invitation(
            invite_organization, invite_request
        )

        assert _invitation(invite_request, invite_organization, user) is None
        invite_request.session.flash.assert_called_once_with(
            "Expired invitation for 'testuser' deleted.", queue="success"
        )
        _assert_revoke_events(
            invite_request, invite_organization, user, org_event, user_event
        )
        for send_email in revoke_emails:
            send_email.assert_not_called()
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organization/foobar/people/"

    @pytest.mark.parametrize("token", ["not-a-signed-token", ""])
    def test_token_invalid(
        self, invite_request, invite_organization, revoke_emails, mocker, token
    ):
        """An invitation whose token no longer verifies (a rotated secret, or a
        corrupt row) can still be revoked."""
        user = UserFactory.create(username="testuser")
        org_event = mocker.patch.object(
            invite_organization, "record_event", autospec=True
        )
        user_event = mocker.patch.object(user, "record_event", autospec=True)
        OrganizationInvitationFactory.create(
            organization=invite_organization, user=user, token=token
        )
        invite_request.POST = MultiDict({"user_id": user.id})

        result = org_views.revoke_organization_invitation(
            invite_organization, invite_request
        )

        assert _invitation(invite_request, invite_organization, user) is None
        invite_request.session.flash.assert_called_once_with(
            "Invalid invitation for 'testuser' deleted.", queue="success"
        )
        _assert_revoke_events(
            invite_request, invite_organization, user, org_event, user_event
        )
        for send_email in revoke_emails:
            send_email.assert_not_called()
        assert isinstance(result, HTTPSeeOther)


class TestReinviteOrganizationMember:
    @pytest.fixture
    def invitee(self):
        user = UserFactory.create(username="testuser")
        EmailFactory.create(user=user, verified=True, primary=True)
        return user

    @pytest.mark.parametrize(
        "make_token",
        [
            lambda token_service: _expired_token(
                token_service, {"action": "email-organization-role-verify"}
            ),
            lambda token_service: "not-a-signed-token",
            lambda token_service: "",
        ],
        ids=["expired", "invalid", "missing"],
    )
    def test_pending_invitation_with_unusable_token_is_replaced(
        self,
        invite_request,
        invite_organization,
        invitee,
        token_service,
        mocker,
        make_token,
    ):
        """
        A pending invitation whose token no longer loads is not an active
        invite, so inviting the user again sends a fresh one.
        """
        OrganizationInvitationFactory.create(
            organization=invite_organization,
            user=invitee,
            invite_status=OrganizationInvitationStatus.Pending,
            token=make_token(token_service),
        )
        mocker.patch.object(
            org_views, "send_organization_member_invited_email", autospec=True
        )
        role_verification_email = mocker.patch.object(
            org_views, "send_organization_role_verification_email", autospec=True
        )
        invite_request.POST = MultiDict(
            {"username": invitee.username, "role_name": "Manager"}
        )

        result = org_views.manage_organization_roles(
            invite_organization, invite_request
        )

        assert isinstance(result, HTTPSeeOther)
        invitation = _invitation(invite_request, invite_organization, invitee)
        assert invitation.invite_status == OrganizationInvitationStatus.Pending
        assert token_service.loads(invitation.token)["desired_role"] == "Manager"
        role_verification_email.assert_called_once()
        invite_request.session.flash.assert_called_once_with(
            "Invitation sent to 'testuser'", queue="success"
        )


class TestChangeOrganizationRole:
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_change_role(self, db_request, orgtype, monkeypatch):
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

    def test_change_organization_role_invalid_role_name(self, db_request):
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

    def test_change_missing_organization_role(self, db_request):
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

    def test_change_own_owner_organization_role(self, db_request):
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
    def test_delete_role(self, db_request, monkeypatch):
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

    def test_delete_missing_role(self, db_request, monkeypatch):
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

    def test_delete_other_role_as_nonowner(self, db_request):
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

    def test_delete_own_owner_role(self, db_request):
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

    def test_delete_non_owner_role(self, db_request):
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
            time=dt.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_event = OrganizationEventFactory.create(
            source=organization,
            tag="fake:event",
            time=dt.datetime(2018, 2, 5, 17, 18, 18, 462_634),
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


class TestManageOrganizationPublishingViews:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory.create()

    @pytest.fixture
    def oidc_limiters(self, mocker):
        """Spied per-user and per-IP OIDC registration rate limiters."""
        limiters = {"user": DummyRateLimiter(), "ip": DummyRateLimiter()}
        for limiter in limiters.values():
            mocker.spy(limiter, "test")
            mocker.spy(limiter, "hit")
        return limiters

    @pytest.fixture
    def publishing_request(self, db_request, pyramid_services, oidc_limiters, mocker):
        """
        A POST-less request from a user with a verified primary email, with
        every trusted publishing provider enabled and the OIDC registration
        rate limiters backed by ``oidc_limiters``.
        """
        db_request.user = UserFactory.create(with_verified_primary_email=True)
        db_request.registry.settings["github.token"] = "fake-api-token"
        db_request.POST = MultiDict()
        db_request.path = "/fake/path"
        mocker.patch.object(
            db_request, "route_url", autospec=True, return_value="/fake/route"
        )
        for flag in (
            AdminFlagValue.DISALLOW_OIDC,
            AdminFlagValue.DISALLOW_GITHUB_OIDC,
            AdminFlagValue.DISALLOW_GITLAB_OIDC,
            AdminFlagValue.DISALLOW_GOOGLE_OIDC,
            AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
        ):
            db_request.db.get(AdminFlag, flag.value).enabled = False
        mocker.spy(db_request.session, "flash")
        for key in ("user", "ip"):
            pyramid_services.register_service(
                oidc_limiters[key],
                IRateLimiter,
                None,
                name=f"{key}_oidc.publisher.register",
            )
        return db_request

    @pytest.fixture
    def lookup_owner(self, mocker):
        """Stub the GitHub API lookup the real form makes."""
        return mocker.patch.object(
            org_views.PendingGitHubPublisherForm,
            "_lookup_owner",
            autospec=True,
            return_value={"login": "test-owner", "id": "12345"},
        )

    @pytest.fixture
    def github_post(self):
        return MultiDict(
            {
                "project_name": "test-project",
                "owner": "test-owner",
                "repository": "test-repo",
                "workflow_filename": "release.yml",
                "environment": "",
            }
        )

    def test_manage_organization_publishing_get(self, publishing_request, organization):
        """Test GET request returns all forms and pending publishers"""
        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.manage_organization_publishing()

        assert result == {
            "organization": organization,
            "pending_github_publisher_form": view.pending_github_publisher_form,
            "pending_gitlab_publisher_form": view.pending_gitlab_publisher_form,
            "pending_google_publisher_form": view.pending_google_publisher_form,
            "pending_activestate_publisher_form": (
                view.pending_activestate_publisher_form
            ),
            "pending_oidc_publishers": organization.pending_oidc_publishers,
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
        }
        publishing_request.session.flash.assert_not_called()

    def test_add_pending_github_oidc_publisher_success(
        self,
        publishing_request,
        organization,
        github_post,
        lookup_owner,
        oidc_limiters,
        metrics,
        mocker,
    ):
        """Test successfully adding a pending GitHub OIDC publisher"""
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert isinstance(result, HTTPSeeOther)
        publisher = publishing_request.db.scalars(
            select(PendingGitHubPublisher).filter_by(organization_id=organization.id)
        ).one()
        assert publisher.project_name == "test-project"
        assert publisher.repository_owner == "test-owner"
        assert publisher.repository_owner_id == "12345"
        assert publisher.added_by == publishing_request.user
        publishing_request.session.flash.assert_called_once_with(
            "Registered a new pending publisher to create the project "
            f"'test-project' owned by the '{organization.name}' organization.",
            queue="success",
        )
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=["publisher:GitHub", "organization:true"],
            ),
            mocker.call(
                "warehouse.oidc.add_pending_publisher.ok",
                tags=["publisher:GitHub", "organization:true"],
            ),
        ]
        oidc_limiters["user"].hit.assert_called_once_with(publishing_request.user.id)
        oidc_limiters["ip"].hit.assert_called_once_with(publishing_request.remote_addr)

    def test_add_pending_oidc_publisher_unverified_email(
        self, publishing_request, organization, github_post, oidc_limiters
    ):
        """A user without a verified primary email is refused before the limits."""
        publishing_request.user = UserFactory.create()
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        publishing_request.session.flash.assert_called_once_with(
            "You must have a verified email in order to register a "
            "pending trusted publisher. "
            "See https://docs.pypi.org/your-account/managing-your-account/"
            "#email-address-verification for details.",
            queue="error",
        )
        oidc_limiters["user"].hit.assert_not_called()
        oidc_limiters["ip"].hit.assert_not_called()
        assert publishing_request.db.scalars(select(PendingGitHubPublisher)).all() == []

    def test_add_pending_oidc_publisher_too_many_already(
        self, publishing_request, organization, github_post, oidc_limiters
    ):
        """The cap counts the user's own pending publishers for this organization."""
        PendingGitHubPublisherFactory.create_batch(
            3, organization_id=organization.id, added_by=publishing_request.user
        )
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        publishing_request.session.flash.assert_called_once_with(
            "You already have 3 pending trusted publishers for this "
            "organization. Remove one before adding another.",
            queue="error",
        )
        oidc_limiters["user"].hit.assert_not_called()
        oidc_limiters["ip"].hit.assert_not_called()
        assert (
            len(
                publishing_request.db.scalars(
                    select(PendingGitHubPublisher).filter_by(
                        organization_id=organization.id
                    )
                ).all()
            )
            == 3
        )

    def test_add_pending_oidc_publisher_other_owners_do_not_count(
        self, publishing_request, organization, github_post, lookup_owner
    ):
        """
        Another owner's pending publishers do not block this user, who could not
        remove them.
        """
        PendingGitHubPublisherFactory.create_batch(3, organization_id=organization.id)
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert isinstance(result, HTTPSeeOther)
        assert (
            publishing_request.db.scalars(
                select(PendingGitHubPublisher).filter_by(
                    organization_id=organization.id, added_by=publishing_request.user
                )
            )
            .one()
            .project_name
            == "test-project"
        )

    def test_add_pending_oidc_publisher_elsewhere_do_not_count(
        self, publishing_request, organization, github_post, lookup_owner
    ):
        """The user's personal and other-organization pending publishers do not
        count toward this organization's limit."""
        PendingGitHubPublisherFactory.create_batch(
            3, added_by=publishing_request.user, organization_id=None
        )
        PendingGitHubPublisherFactory.create_batch(
            3,
            added_by=publishing_request.user,
            organization_id=OrganizationFactory.create().id,
        )
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert isinstance(result, HTTPSeeOther)
        assert (
            publishing_request.db.scalars(
                select(PendingGitHubPublisher).filter_by(
                    organization_id=organization.id
                )
            )
            .one()
            .added_by
            == publishing_request.user
        )

    @pytest.mark.parametrize(
        ("limiter_name", "other_limiter_name"), [("user", "ip"), ("ip", "user")]
    )
    def test_add_pending_oidc_publisher_ratelimited(
        self,
        publishing_request,
        pyramid_services,
        organization,
        github_post,
        oidc_limiters,
        metrics,
        mocker,
        limiter_name,
        other_limiter_name,
    ):
        """A rate-limited registration spends neither limiter and writes nothing."""
        limiter = mocker.create_autospec(RateLimiter, instance=True)
        limiter.test.return_value = False
        limiter.resets_in.return_value = dt.timedelta(seconds=60)
        pyramid_services.register_service(
            limiter, IRateLimiter, None, name=f"{limiter_name}_oidc.publisher.register"
        )
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        with pytest.raises(HTTPTooManyRequests) as exc:
            view.add_pending_github_oidc_publisher()

        assert exc.value.headers["Retry-After"] == "60"
        limiter.test.assert_called_once_with(
            publishing_request.user.id
            if limiter_name == "user"
            else publishing_request.remote_addr
        )
        limiter.hit.assert_not_called()
        oidc_limiters[other_limiter_name].hit.assert_not_called()
        publishing_request.session.flash.assert_not_called()
        assert publishing_request.db.scalars(select(PendingGitHubPublisher)).all() == []
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=["publisher:GitHub", "organization:true"],
            ),
            mocker.call(
                "warehouse.oidc.add_pending_publisher.ratelimited",
                tags=["publisher:GitHub", "organization:true"],
            ),
        ]

    def test_add_pending_oidc_publisher_ratelimited_without_reset_hint(
        self, publishing_request, pyramid_services, organization, github_post, mocker
    ):
        """A limiter that cannot say when it resets still gives a 429."""
        limiter = mocker.create_autospec(RateLimiter, instance=True)
        limiter.test.return_value = False
        limiter.resets_in.return_value = None
        pyramid_services.register_service(
            limiter, IRateLimiter, None, name="user_oidc.publisher.register"
        )
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        with pytest.raises(HTTPTooManyRequests) as exc:
            view.add_pending_github_oidc_publisher()

        assert "Retry-After" not in exc.value.headers

    def test_add_pending_github_oidc_publisher_disabled(
        self, publishing_request, organization
    ):
        """Test adding GitHub publisher when admin flag disables it"""
        publishing_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_GITHUB_OIDC.value
        ).enabled = True

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        assert result["disabled"]["GitHub"] is True
        publishing_request.session.flash.assert_called_once_with(
            "GitHub-based trusted publishing is temporarily disabled. "
            "See https://docs.pypi.org/about/security-and-internals/"
            "#temporarily-disabled-features for details.",
            queue="error",
        )

    def test_add_pending_github_oidc_publisher_invalid_form(
        self, publishing_request, organization
    ):
        """Adding a GitHub publisher with an empty form flashes an error"""
        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        publishing_request.session.flash.assert_called_once_with(
            "The trusted publisher could not be registered",
            queue="error",
        )

    def test_add_pending_gitlab_oidc_publisher_success(
        self, publishing_request, organization, metrics, mocker
    ):
        """Test successfully adding a pending GitLab OIDC publisher"""
        publishing_request.POST = MultiDict(
            {
                "project_name": "test-project",
                "namespace": "test-namespace",
                "project": "test-project",
                "workflow_filepath": ".gitlab-ci.yml",
                "environment": "",
                "issuer_url": "https://gitlab.com",
            }
        )

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_gitlab_oidc_publisher()

        assert isinstance(result, HTTPSeeOther)
        publisher = publishing_request.db.scalars(
            select(PendingGitLabPublisher).filter_by(organization_id=organization.id)
        ).one()
        assert publisher.namespace == "test-namespace"
        assert metrics.increment.call_args_list[-1] == mocker.call(
            "warehouse.oidc.add_pending_publisher.ok",
            tags=["publisher:GitLab", "organization:true"],
        )

    def test_gitlab_form_includes_issuer_url_choices(
        self, publishing_request, organization
    ):
        """The GitLab form offers the organization's custom GitLab issuers"""
        OrganizationOIDCIssuerFactory.create(
            organization=organization,
            issuer_type=OIDCIssuerType.GitLab,
            issuer_url="https://gitlab.example.com",
        )

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )

        assert view.pending_gitlab_publisher_form.issuer_url.choices == [
            ("https://gitlab.com", "https://gitlab.com"),
            ("https://gitlab.example.com", "https://gitlab.example.com"),
        ]

    def test_manage_organization_publishing_get_oidc_disabled(
        self, publishing_request, organization
    ):
        """Test GET request when global OIDC is disabled"""
        publishing_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_OIDC.value
        ).enabled = True

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.manage_organization_publishing()

        assert result == view.default_response
        assert result["disabled"] == {
            "GitHub": True,
            "GitLab": True,
            "Google": True,
            "ActiveState": True,
        }
        publishing_request.session.flash.assert_called_once_with(
            "Trusted publishing is temporarily disabled. "
            "See https://docs.pypi.org/about/security-and-internals/"
            "#temporarily-disabled-features for details.",
            queue="error",
        )

    def test_add_pending_github_oidc_publisher_already_exists(
        self, publishing_request, organization, github_post, lookup_owner
    ):
        """Test adding GitHub publisher when it already exists"""
        PendingGitHubPublisherFactory.create(
            project_name="test-project",
            repository_name="test-repo",
            repository_owner="test-owner",
            repository_owner_id="12345",
            workflow_filename="release.yml",
            environment="",
            organization_id=organization.id,
        )
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        publishing_request.session.flash.assert_called_once_with(
            "This trusted publisher has already been registered. "
            "Please contact PyPI's admins if this wasn't intentional.",
            queue="error",
        )

    def test_add_pending_github_oidc_publisher_unique_violation(
        self, publishing_request, organization, github_post, lookup_owner
    ):
        """A UniqueViolation raised by the INSERT during ``flush()`` (another
        pending publisher already targets the same external identity under a
        different ``project_name``) rolls back the now-aborted transaction so
        the session stays usable for the end-of-request commit, and tells the
        user about the conflict. Regression test for GH-20006.
        """
        # A pending publisher with the same external identity but a *different*
        # project_name. The early duplicate-check query keys on project_name so
        # it misses this row, but the DB unique constraint does not -- so the
        # next conflicting insert raises a real UniqueViolation during flush().
        PendingGitHubPublisherFactory.create(
            project_name="test-project-existing",
            repository_name="test-repo",
            repository_owner="test-owner",
            repository_owner_id="12345",
            workflow_filename="release.yml",
            environment="",
            organization_id=organization.id,
        )
        publishing_request.db.flush()
        publishing_request.POST = github_post

        view = org_views.ManageOrganizationPublishingViews(
            organization, publishing_request
        )
        result = view.add_pending_github_oidc_publisher()

        assert result == view.default_response
        publishing_request.session.flash.assert_called_once_with(
            "A pending trusted publisher matching this configuration "
            "has already been registered for a different project name. "
            "Please contact PyPI's admins if this wasn't intentional.",
            queue="error",
        )
        # The conflicting INSERT left the transaction aborted. Without an
        # explicit rollback in the handler this query raises PendingRollbackError
        # -- which is what surfaces to the user as a 500/503. The rollback also
        # discards this request's uncommitted work, including the pre-existing
        # publisher created above, so the count is 0.
        assert publishing_request.db.query(PendingGitHubPublisher).count() == 0

    def test_two_orgs_can_create_pending_publishers_for_same_project_name(
        self, publishing_request, lookup_owner
    ):
        """
        Two different organizations can create pending OIDC publishers
        for the same future project name but with different OIDC credentials.
        """
        # Create two separate organizations with different owners
        org1_owner = UserFactory.create(username="org1-owner")
        org2_owner = UserFactory.create(username="org2-owner")
        EmailFactory.create(user=org1_owner, verified=True, primary=True)
        EmailFactory.create(user=org2_owner, verified=True, primary=True)

        org1 = OrganizationFactory.create(name="org1")
        org2 = OrganizationFactory.create(name="org2")

        OrganizationRoleFactory.create(
            organization=org1, user=org1_owner, role_name="Owner"
        )
        OrganizationRoleFactory.create(
            organization=org2, user=org2_owner, role_name="Owner"
        )

        # Setup request for org1
        publishing_request.user = org1_owner
        publishing_request.POST = MultiDict(
            {
                "project_name": "same-project-name",
                "owner": "org1",
                "repository": "repo1",
                "workflow_filename": "release.yml",
                "environment": "",
            }
        )
        lookup_owner.return_value = {"login": "org1", "id": "11111"}

        # Org1 creates a pending publisher
        view1 = org_views.ManageOrganizationPublishingViews(org1, publishing_request)
        result1 = view1.add_pending_github_oidc_publisher()
        assert isinstance(result1, HTTPSeeOther)

        # Verify org1's pending publisher was created
        pending_publisher_1 = (
            publishing_request.db.query(PendingGitHubPublisher)
            .filter(
                PendingGitHubPublisher.organization_id == org1.id,
                PendingGitHubPublisher.project_name == "same-project-name",
            )
            .one()
        )
        assert pending_publisher_1.repository_owner == "org1"
        assert pending_publisher_1.repository_name == "repo1"
        assert pending_publisher_1.organization_id == org1.id

        # Setup request for org2 with SAME project name but different credentials
        publishing_request.user = org2_owner
        publishing_request.POST = MultiDict(
            {
                "project_name": "same-project-name",  # SAME PROJECT NAME
                "owner": "org2",  # DIFFERENT GitHub org
                "repository": "repo2",  # DIFFERENT repo
                "workflow_filename": "release.yml",
                "environment": "",
            }
        )
        lookup_owner.return_value = {"login": "org2", "id": "22222"}

        # Org2 creates a pending publisher for the SAME project name
        view2 = org_views.ManageOrganizationPublishingViews(org2, publishing_request)
        result2 = view2.add_pending_github_oidc_publisher()
        assert isinstance(result2, HTTPSeeOther)

        # Verify org2's pending publisher was also created
        pending_publisher_2 = (
            publishing_request.db.query(PendingGitHubPublisher)
            .filter(
                PendingGitHubPublisher.organization_id == org2.id,
                PendingGitHubPublisher.project_name == "same-project-name",
            )
            .one()
        )
        assert pending_publisher_2.repository_owner == "org2"
        assert pending_publisher_2.repository_name == "repo2"
        assert pending_publisher_2.organization_id == org2.id

        # CRITICAL: Both pending publishers should exist
        all_pending_publishers = (
            publishing_request.db.query(PendingGitHubPublisher)
            .filter(PendingGitHubPublisher.project_name == "same-project-name")
            .all()
        )
        assert len(all_pending_publishers) == 2

        # Verify they have different credentials (different organizations)
        assert pending_publisher_1.id != pending_publisher_2.id
        assert (
            pending_publisher_1.repository_owner != pending_publisher_2.repository_owner
        )
        assert (
            pending_publisher_1.repository_name != pending_publisher_2.repository_name
        )
