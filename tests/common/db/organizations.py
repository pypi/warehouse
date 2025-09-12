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

from warehouse.observations.models import ObservationKind
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationNameCatalog,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationStripeCustomer,
    OrganizationStripeSubscription,
    Team,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRole,
    TeamRoleType,
)

from .accounts import UserFactory
from .base import WarehouseFactory
from .observations import ObserverFactory
from .packaging import ProjectFactory
from .subscriptions import StripeCustomerFactory, StripeSubscriptionFactory

fake = faker.Faker()


class OrganizationApplicationFactory(WarehouseFactory):
    class Meta:
        model = OrganizationApplication

    id = factory.Faker("uuid4", cast_to=None)
    name = factory.Faker("pystr", max_chars=12)
    display_name = factory.Faker("word")
    orgtype = "Community"
    link_url = factory.Faker("uri")
    description = factory.Faker("sentence")
    status = OrganizationApplicationStatus.Submitted
    submitted_by = factory.SubFactory(UserFactory)
    submitted = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )


class OrganizationApplicationObservationFactory(WarehouseFactory):
    class Meta:
        model = OrganizationApplication.Observation

    related = factory.SubFactory(OrganizationApplicationFactory)
    related_name = factory.LazyAttribute(lambda o: repr(o.related))
    observer = factory.SubFactory(ObserverFactory)

    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )
    kind = ObservationKind.InformationRequest.value[0]
    payload = factory.Faker("json")
    summary = factory.Faker("paragraph")


class OrganizationFactory(WarehouseFactory):
    class Meta:
        model = Organization

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        organization = super()._create(model_class, *args, **kwargs)
        OrganizationNameCatalogFactory.create(
            normalized_name=organization.normalized_name,
            organization_id=organization.id,
        )
        return organization

    id = factory.Faker("uuid4", cast_to=None)
    name = factory.Faker("pystr", max_chars=12)
    display_name = factory.Faker("word")
    orgtype = "Community"
    link_url = factory.Faker("uri")
    description = factory.Faker("sentence")
    is_active = True
    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )


class OrganizationEventFactory(WarehouseFactory):
    class Meta:
        model = Organization.Event

    source = factory.SubFactory(OrganizationFactory)


class OrganizationNameCatalogFactory(WarehouseFactory):
    class Meta:
        model = OrganizationNameCatalog

    normalized_name = factory.Faker("pystr", max_chars=12)
    organization_id = factory.Faker("uuid4", cast_to=None)


class OrganizationRoleFactory(WarehouseFactory):
    class Meta:
        model = OrganizationRole

    role_name = OrganizationRoleType.Owner
    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)


class OrganizationInvitationFactory(WarehouseFactory):
    class Meta:
        model = OrganizationInvitation

    invite_status = "pending"
    token = "test_token"
    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)


class OrganizationProjectFactory(WarehouseFactory):
    class Meta:
        model = OrganizationProject

    id = factory.Faker("uuid4", cast_to=None)
    organization = factory.SubFactory(OrganizationFactory)
    project = factory.SubFactory(ProjectFactory)


class OrganizationStripeSubscriptionFactory(WarehouseFactory):
    class Meta:
        model = OrganizationStripeSubscription

    id = factory.Faker("uuid4", cast_to=None)
    organization = factory.SubFactory(OrganizationFactory)
    subscription = factory.SubFactory(StripeSubscriptionFactory)


class OrganizationStripeCustomerFactory(WarehouseFactory):
    class Meta:
        model = OrganizationStripeCustomer

    id = factory.Faker("uuid4", cast_to=None)
    organization = factory.SubFactory(OrganizationFactory)
    customer = factory.SubFactory(StripeCustomerFactory)


class TeamFactory(WarehouseFactory):
    class Meta:
        model = Team

    id = factory.Faker("uuid4", cast_to=None)
    name = factory.Faker("pystr", max_chars=12)
    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )
    organization = factory.SubFactory(OrganizationFactory)


class TeamEventFactory(WarehouseFactory):
    class Meta:
        model = Team.Event

    source = factory.SubFactory(TeamFactory)


class TeamRoleFactory(WarehouseFactory):
    class Meta:
        model = TeamRole

    role_name = TeamRoleType.Member
    user = factory.SubFactory(UserFactory)
    team = factory.SubFactory(TeamFactory)


class TeamProjectRoleFactory(WarehouseFactory):
    class Meta:
        model = TeamProjectRole

    role_name = TeamProjectRoleType.Owner
    project = factory.SubFactory(ProjectFactory)
    team = factory.SubFactory(TeamFactory)
