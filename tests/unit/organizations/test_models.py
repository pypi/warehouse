# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.authorization import Allow
from pyramid.httpexceptions import HTTPPermanentRedirect
from pyramid.location import lineage

from warehouse.authnz import Permissions
from warehouse.organizations.models import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationRoleType,
    TeamFactory,
)

from ...common.db.organizations import (
    OrganizationApplicationFactory as DBOrganizationApplicationFactory,
    OrganizationFactory as DBOrganizationFactory,
    OrganizationManualActivationFactory as DBOrganizationManualActivationFactory,
    OrganizationNameCatalogFactory as DBOrganizationNameCatalogFactory,
    OrganizationRoleFactory as DBOrganizationRoleFactory,
    OrganizationStripeCustomerFactory as DBOrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory as DBOrganizationStripeSubscriptionFactory,
    TeamFactory as DBTeamFactory,
)
from ...common.db.subscriptions import (
    StripeCustomerFactory as DBStripeCustomerFactory,
    StripeSubscriptionFactory as DBStripeSubscriptionFactory,
)


class TestOrganizationApplicationFactory:
    def test_traversal_finds(self, db_request):
        organization_application = DBOrganizationApplicationFactory.create()
        _organization_application = OrganizationApplicationFactory(db_request)
        assert (
            _organization_application[organization_application.id]
            == organization_application
        )

    def test_traversal_cant_find(self, db_request):
        DBOrganizationApplicationFactory.create()
        _organization_application = OrganizationApplicationFactory(db_request)
        with pytest.raises(KeyError):
            _organization_application["deadbeef-dead-beef-dead-beefdeadbeef"]


class TestOrganizationApplication:
    def test_acl(self, db_session):
        organization_application = DBOrganizationApplicationFactory.create()
        assert organization_application.__acl__() == [
            (
                Allow,
                f"user:{organization_application.submitted_by.id}",
                (Permissions.OrganizationApplicationsManage,),
            )
        ]


class TestOrganizationFactory:
    @pytest.mark.parametrize(("name", "normalized"), [("foo", "foo"), ("Bar", "bar")])
    def test_traversal_finds(self, db_request, name, normalized):
        organization = DBOrganizationFactory.create(name=name)
        root = OrganizationFactory(db_request)

        assert root[normalized] == organization

    def test_traversal_redirects(self, db_request):
        db_request.matched_route = pretend.stub(generate=lambda *a, **kw: "route-path")
        organization = DBOrganizationFactory.create()
        DBOrganizationNameCatalogFactory.create(
            normalized_name="oldname",
            organization_id=organization.id,
        )
        root = OrganizationFactory(db_request)

        with pytest.raises(HTTPPermanentRedirect):
            root["oldname"]

    def test_traversal_cant_find(self, db_request):
        organization = DBOrganizationFactory.create()
        root = OrganizationFactory(db_request)

        with pytest.raises(KeyError):
            root[organization.name + "invalid"]


class TestOrganization:
    def test_customer_name(self, db_session):
        organization = DBOrganizationFactory.create(
            name="pypi", display_name="The Python Package Index"
        )
        assert (
            organization.customer_name()
            == "PyPI Organization - The Python Package Index (pypi)"
        )
        assert (
            organization.customer_name("Test PyPI")
            == "Test PyPI Organization - The Python Package Index (pypi)"
        )

    def test_acl(self, db_session):
        organization = DBOrganizationFactory.create()
        owner1 = DBOrganizationRoleFactory.create(organization=organization)
        owner2 = DBOrganizationRoleFactory.create(organization=organization)
        billing_mgr1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.BillingManager
        )
        billing_mgr2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.BillingManager
        )
        account_mgr1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Manager
        )
        account_mgr2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Manager
        )
        member1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Member
        )
        member2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Member
        )

        acls = [
            item for location in lineage(organization) for item in location.__acl__()
        ]

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminOrganizationsRead,
                    Permissions.AdminOrganizationsWrite,
                    Permissions.AdminOrganizationsNameWrite,
                ),
            ),
            (Allow, "group:moderators", Permissions.AdminOrganizationsRead),
        ] + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsManage,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationsBillingManage,
                        Permissions.OrganizationProjectsAdd,
                        Permissions.OrganizationProjectsRemove,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsManage,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationsBillingManage,
                        Permissions.OrganizationProjectsAdd,
                        Permissions.OrganizationProjectsRemove,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{billing_mgr1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsBillingManage,
                    ],
                ),
                (
                    Allow,
                    f"user:{billing_mgr2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsBillingManage,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{account_mgr1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationProjectsAdd,
                    ],
                ),
                (
                    Allow,
                    f"user:{account_mgr2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationProjectsAdd,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{member1.user.id}",
                    [Permissions.OrganizationsRead, Permissions.OrganizationTeamsRead],
                ),
                (
                    Allow,
                    f"user:{member2.user.id}",
                    [Permissions.OrganizationsRead, Permissions.OrganizationTeamsRead],
                ),
            ],
            key=lambda x: x[1],
        )

    def test_record_event_with_geoip(self, db_request):
        """
        Test to cover condition when record_event is called with geoip_info as
        part of the inbound request.
        Possibly could be removed once more comprehensive tests are in place,
        but nothing explicitly covers `HasEvents.record_event`
        """
        db_request.ip_address.geoip_info = {"country_name": "United States"}

        organization = DBOrganizationFactory.create()

        organization.record_event(
            tag="",
            request=db_request,
            additional={},
        )

        event = organization.events[0]

        assert event.additional == {
            "organization_name": organization.name,
            "geoip_info": {"country_name": "United States"},
        }
        assert event.location_info == "United States"

    def test_location_info_without_geoip(self, db_request):
        organization = DBOrganizationFactory.create()
        organization.record_event(
            tag="",
            request=db_request,
            additional={},
        )

        event = organization.events[0]

        assert event.additional == {
            "organization_name": organization.name,
        }
        assert event.location_info == db_request.ip_address

    def test_location_info_with_partial(self, db_request):
        db_request.ip_address.geoip_info = {"country_code3": "USA"}

        organization = DBOrganizationFactory.create()
        organization.record_event(
            tag="",
            request=db_request,
            additional={},
        )

        event = organization.events[0]

        assert event.additional == {
            "organization_name": organization.name,
            "geoip_info": {"country_code3": "USA"},
        }
        assert event.location_info == db_request.ip_address


class TestTeamFactory:
    def test_traversal_finds(self, db_request):
        organization = DBOrganizationFactory.create(name="foo")
        team = DBTeamFactory.create(organization=organization, name="Bar")

        root = TeamFactory(db_request)

        assert root["foo"]["bar"] == team

    def test_traversal_cant_find(self, db_request):
        organization = DBOrganizationFactory.create(name="foo")
        DBTeamFactory.create(organization=organization, name="Bar")

        root = TeamFactory(db_request)

        with pytest.raises(KeyError):
            root["foo"]["invalid"]


class TestTeam:
    def test_acl(self, db_session):
        organization = DBOrganizationFactory.create()
        team = DBTeamFactory.create(organization=organization)
        owner1 = DBOrganizationRoleFactory.create(organization=organization)
        owner2 = DBOrganizationRoleFactory.create(organization=organization)
        billing_mgr1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.BillingManager
        )
        billing_mgr2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.BillingManager
        )
        account_mgr1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Manager
        )
        account_mgr2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Manager
        )
        member1 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Member
        )
        member2 = DBOrganizationRoleFactory.create(
            organization=organization, role_name=OrganizationRoleType.Member
        )

        acls = [item for location in lineage(team) for item in location.__acl__()]

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminOrganizationsRead,
                    Permissions.AdminOrganizationsWrite,
                    Permissions.AdminOrganizationsNameWrite,
                ),
            ),
            (Allow, "group:moderators", Permissions.AdminOrganizationsRead),
        ] + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsManage,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationsBillingManage,
                        Permissions.OrganizationProjectsAdd,
                        Permissions.OrganizationProjectsRemove,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsManage,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationsBillingManage,
                        Permissions.OrganizationProjectsAdd,
                        Permissions.OrganizationProjectsRemove,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{billing_mgr1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsBillingManage,
                    ],
                ),
                (
                    Allow,
                    f"user:{billing_mgr2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationsBillingManage,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{account_mgr1.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationProjectsAdd,
                    ],
                ),
                (
                    Allow,
                    f"user:{account_mgr2.user.id}",
                    [
                        Permissions.OrganizationsRead,
                        Permissions.OrganizationTeamsRead,
                        Permissions.OrganizationTeamsManage,
                        Permissions.OrganizationProjectsAdd,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{member1.user.id}",
                    [Permissions.OrganizationsRead, Permissions.OrganizationTeamsRead],
                ),
                (
                    Allow,
                    f"user:{member2.user.id}",
                    [Permissions.OrganizationsRead, Permissions.OrganizationTeamsRead],
                ),
            ],
            key=lambda x: x[1],
        )

    def test_active_subscription(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(customer=stripe_customer)
        DBOrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        assert organization.active_subscription is not None
        assert organization.manageable_subscription is not None

    def test_active_subscription_none(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer=stripe_customer,
            status="unpaid",
        )
        DBOrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        assert organization.active_subscription is None
        assert organization.manageable_subscription is not None

    def test_manageable_subscription(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(customer=stripe_customer)
        DBOrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        assert organization.active_subscription is not None
        assert organization.manageable_subscription is not None

    def test_manageable_subscription_none(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer=stripe_customer,
            status="canceled",
        )
        DBOrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        assert organization.active_subscription is None
        assert organization.manageable_subscription is None

    def test_good_standing_with_manual_activation_active(self, db_session):
        import datetime

        organization = DBOrganizationFactory.create(orgtype="Company")
        DBOrganizationManualActivationFactory.create(
            organization=organization,
            expires=datetime.datetime(2025, 12, 31, 23, 59, 0, tzinfo=datetime.UTC),
        )
        assert organization.good_standing

    def test_good_standing_with_manual_activation_expired(self, db_session):
        import datetime

        organization = DBOrganizationFactory.create(orgtype="Company")
        DBOrganizationManualActivationFactory.create(
            organization=organization,
            expires=datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.UTC),
        )
        assert not organization.good_standing

    def test_good_standing_community_without_manual_activation(self, db_session):
        organization = DBOrganizationFactory.create(orgtype="Community")
        assert organization.good_standing

    def test_good_standing_company_without_manual_activation_or_subscription(
        self, db_session
    ):
        organization = DBOrganizationFactory.create(orgtype="Company")
        assert not organization.good_standing


class TestOrganizationManualActivation:
    def test_is_active_future_expiration(self, db_session):
        import datetime

        activation = DBOrganizationManualActivationFactory.create(
            expires=datetime.datetime(2025, 12, 31, 23, 59, 0, tzinfo=datetime.UTC)
        )
        assert activation.is_active

    def test_is_active_past_expiration(self, db_session):
        import datetime

        activation = DBOrganizationManualActivationFactory.create(
            expires=datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
        )
        assert not activation.is_active

    def test_current_member_count(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=10
        )

        # Create some organization roles (members)
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(3):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert activation.current_member_count == 3

    def test_has_available_seats_with_space(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=10
        )

        # Create some organization roles (members)
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(5):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert activation.has_available_seats

    def test_has_available_seats_at_limit(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=5
        )

        # Create organization roles up to the limit
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(5):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert not activation.has_available_seats

    def test_has_available_seats_over_limit(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=3
        )

        # Create more organization roles than the limit allows
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(5):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert not activation.has_available_seats

    def test_available_seats(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=10
        )

        # Create some organization roles (members)
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(3):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert activation.available_seats == 7  # 10 - 3

    def test_available_seats_negative(self, db_session):
        organization = DBOrganizationFactory.create()
        activation = DBOrganizationManualActivationFactory.create(
            organization=organization, seat_limit=3
        )

        # Create more organization roles than the limit
        from ...common.db.accounts import UserFactory as DBUserFactory

        for _ in range(5):
            user = DBUserFactory.create()
            DBOrganizationRoleFactory.create(
                organization=organization,
                user=user,
                role_name=OrganizationRoleType.Member,
            )

        assert activation.available_seats == 0  # Should never be negative
