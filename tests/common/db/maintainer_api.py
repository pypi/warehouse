# SPDX-License-Identifier: Apache-2.0

import datetime as dt

import factory

from warehouse.api.maintainer import (
    ApiKey,
    ApiKeyScope,
    generate_api_key,
    hash_api_key,
)
from warehouse.utils import now

from .accounts import UserFactory
from .base import WarehouseFactory


class ApiKeyFactory(WarehouseFactory):
    class Meta:
        model = ApiKey

    class Params:
        # Pass raw_key to authenticate with the key a test holds.
        raw_key = factory.LazyFunction(generate_api_key)

    user = factory.SubFactory(UserFactory)
    created_by_id = factory.SelfAttribute("user.id")
    name = factory.Faker("pystr", max_chars=12)
    hashed_key = factory.LazyAttribute(lambda o: hash_api_key(o.raw_key))
    last_four = factory.LazyAttribute(lambda o: o.raw_key[-4:])
    scopes = factory.LazyFunction(lambda: [ApiKeyScope.TestEcho.value])
    expires = factory.LazyFunction(lambda: now() + dt.timedelta(days=30))
