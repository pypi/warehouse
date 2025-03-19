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

        acls = []
        for location in lineage(organization):
            try:
                acl = location.__acl__
            except AttributeError:
                continue

            if acl and callable(acl):
                acl = acl()

            acls.extend(acl)

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminOrganizationsRead,
                    Permissions.AdminOrganizationsWrite,
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

        acls = []
        for location in lineage(team):
            try:
                acl = location.__acl__
            except AttributeError:
                continue

            if acl and callable(acl):
                acl = acl()

            acls.extend(acl)

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminOrganizationsRead,
                    Permissions.AdminOrganizationsWrite,
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
