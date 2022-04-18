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

from zope.interface.verify import verifyClass

from warehouse.organizations import services
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import OrganizationRoleType

from ...common.db.organizations import OrganizationFactory, UserFactory


def test_database_organizations_factory():
    db = pretend.stub()
    remote_addr = pretend.stub()
    context = pretend.stub()
    request = pretend.stub(db=db, remote_addr=remote_addr)

    service = services.database_organization_factory(context, request)
    assert service.db is db
    assert service.remote_addr is remote_addr


class TestDatabaseOrganizationService:
    def test_verify_service(self):
        assert verifyClass(IOrganizationService, services.DatabaseOrganizationService)

    def test_service_creation(self, remote_addr):
        session = pretend.stub()
        service = services.DatabaseOrganizationService(session, remote_addr=remote_addr)

        assert service.db is session
        assert service.remote_addr is remote_addr

    def test_get_organization(self, organization_service):
        organization = OrganizationFactory.create()
        assert organization_service.get_organization(organization.id) == organization

    def test_get_organization_by_name(self, organization_service):
        organization = OrganizationFactory.create()
        assert (
            organization_service.get_organization_by_name(organization.name)
            == organization
        )

    def test_find_organizationid(self, organization_service):
        organization = OrganizationFactory.create()
        assert (
            organization_service.find_organizationid(organization.name)
            == organization.id
        )

    def test_find_organizationid_nonexistent_org(self, organization_service):
        assert organization_service.find_organizationid("a_spoon_in_the_matrix") is None

    def test_add_organization(self, organization_service):
        organization = OrganizationFactory.create()
        new_org = organization_service.add_organization(
            name=organization.name,
            display_name=organization.display_name,
            orgtype=organization.orgtype,
            link_url=organization.link_url,
            description=organization.description,
        )
        organization_service.db.flush()
        org_from_db = organization_service.get_organization(new_org.id)

        assert org_from_db.name == organization.name
        assert org_from_db.display_name == organization.display_name
        assert org_from_db.orgtype == organization.orgtype
        assert org_from_db.link_url == organization.link_url
        assert org_from_db.description == organization.description
        assert not org_from_db.is_active

    def test_add_catalog_entry(self, organization_service):
        organization = OrganizationFactory.create()

        catalog_entry = organization_service.add_catalog_entry(
            organization.name, organization.id
        )
        assert catalog_entry.name == organization.name
        assert catalog_entry.organization_id == organization.id

    def test_add_organization_role(self, organization_service, user_service):
        user = UserFactory.create()
        organization = OrganizationFactory.create()

        added_role = organization_service.add_organization_role(
            OrganizationRoleType.Owner.value, user.id, organization.id
        )
        assert added_role.role_name == OrganizationRoleType.Owner.value
        assert added_role.user_id == user.id
        assert added_role.organization_id == organization.id

    def test_approve_organization(self, organization_service):
        organization = OrganizationFactory.create()
        organization_service.approve_organization(organization.id)

        assert organization.is_active is True
        assert organization.is_approved is True
        assert organization.date_approved is not None

    def test_decline_organization(self, organization_service):
        organization = OrganizationFactory.create()
        organization_service.decline_organization(organization.id)

        assert organization.is_approved is False
        assert organization.date_approved is not None

    # def test_record_event(self, organization_id, *, tag, additional=None):
    #     raise NotImplementedError
