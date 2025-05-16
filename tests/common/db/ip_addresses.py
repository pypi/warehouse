# SPDX-License-Identifier: Apache-2.0

import hashlib

import factory
import faker

from warehouse.ip_addresses.models import IpAddress

from .base import WarehouseFactory

fake = faker.Faker()


class IpAddressFactory(WarehouseFactory):
    class Meta:
        model = IpAddress

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    ip_address = factory.Sequence(lambda _: fake.unique.ipv4_private())

    hashed_ip_address = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.ip_address.encode("utf8")).hexdigest()
    )
