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

from warehouse.organizations.models import (
    OrganizationFactory,
    OrganizationRoleType,
    TeamFactory,
)

from ...common.db.organizations import (
    OrganizationFactory as DBOrganizationFactory,
    OrganizationNameCatalogFactory as DBOrganizationNameCatalogFactory,
    OrganizationRoleFactory as DBOrganizationRoleFactory,
    TeamFactory as DBTeamFactory,
)


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
            (Allow, "group:admins", "admin"),
            (Allow, "group:moderators", "moderator"),
        ] + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        "view:organization",
                        "view:team",
                        "manage:organization",
                        "manage:team",
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        "view:organization",
                        "view:team",
                        "manage:organization",
                        "manage:team",
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{billing_mgr1.user.id}",
                    ["view:organization", "view:team", "manage:billing"],
                ),
                (
                    Allow,
                    f"user:{billing_mgr2.user.id}",
                    ["view:organization", "view:team", "manage:billing"],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{account_mgr1.user.id}",
                    ["view:organization", "view:team", "manage:team"],
                ),
                (
                    Allow,
                    f"user:{account_mgr2.user.id}",
                    ["view:organization", "view:team", "manage:team"],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (Allow, f"user:{member1.user.id}", ["view:organization", "view:team"]),
                (Allow, f"user:{member2.user.id}", ["view:organization", "view:team"]),
            ],
            key=lambda x: x[1],
        )


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
            (Allow, "group:admins", "admin"),
            (Allow, "group:moderators", "moderator"),
        ] + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        "view:organization",
                        "view:team",
                        "manage:organization",
                        "manage:team",
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        "view:organization",
                        "view:team",
                        "manage:organization",
                        "manage:team",
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{billing_mgr1.user.id}",
                    ["view:organization", "view:team", "manage:billing"],
                ),
                (
                    Allow,
                    f"user:{billing_mgr2.user.id}",
                    ["view:organization", "view:team", "manage:billing"],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{account_mgr1.user.id}",
                    ["view:organization", "view:team", "manage:team"],
                ),
                (
                    Allow,
                    f"user:{account_mgr2.user.id}",
                    ["view:organization", "view:team", "manage:team"],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (Allow, f"user:{member1.user.id}", ["view:organization", "view:team"]),
                (Allow, f"user:{member2.user.id}", ["view:organization", "view:team"]),
            ],
            key=lambda x: x[1],
        )
