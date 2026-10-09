# SPDX-License-Identifier: Apache-2.0

import datetime

import factory

from warehouse.api.maintainer import ApiKey, ApiKeyScope

from .accounts import UserFactory
from .base import WarehouseFactory


class ApiKeyFactory(WarehouseFactory):
    class Meta:
        model = ApiKey

    user = factory.SubFactory(UserFactory)
    created_by_id = factory.SelfAttribute("user.id")
    name = factory.Faker("pystr", max_chars=12)
    hashed_key = factory.Faker("sha256")
    last_four = factory.Faker("pystr", min_chars=4, max_chars=4)
    scopes = factory.LazyFunction(lambda: [ApiKeyScope.ProjectReleasesYank.value])
    expires = factory.LazyFunction(
        lambda: datetime.datetime.now() + datetime.timedelta(days=30)
    )
