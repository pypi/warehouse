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

import factory
import faker

from warehouse.rganizations.models import (
    Organization,
    OrganizationNameCatalog,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleInvitation,
)

from .accounts import UserFactory
from .base import WarehouseFactory
from .packaging import ProjectFactory

fake = faker.Faker()


class OrganizationFactory(WarehouseFactory):
    class Meta:
        model = Organization

    id = factory.Faker("uuid4", cast_to=None)
    name = factory.Faker("name")
    normalized_name = factory.Faker("norm")
    display_name = factory.Faker("display")
    orgtype = factory.Faker("Community")
    link_url = factory.Faker("uri")
    description = factory.Faker("description")
    is_active = True
    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )
    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)


class OrganizationNameCatalogFactory(WarehouseFactory):
    class Meta:
        model = OrganizationNameCatalog

    name = factory.Faker("orgname")
    organization_id = factory.Faker("uuid4", cast_to=None)


class OrganizationRoleFactory(WarehouseFactory):
    class Meta:
        model = OrganizationRole

    role_name = "Owner"
    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)


class OrganizationRoleInvitationFactory(WarehouseFactory):
    class Meta:
        model = OrganizationRoleInvitation

    invite_status = "pending"
    token = "test_token"
    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)


class OrganizationProjectFactory(WarehouseFactory):
    class Meta:
        model = OrganizationProject

    id = factory.Faker("uuid4", cast_to=None)
    is_active = True
    organization = factory.SubFactory(OrganizationFactory)
    project = factory.SubFactory(ProjectFactory)
