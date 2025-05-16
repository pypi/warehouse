# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.macaroons.models import Macaroon

from .base import WarehouseFactory


class MacaroonFactory(WarehouseFactory):
    class Meta:
        model = Macaroon

    description = factory.Faker("pystr", max_chars=12)
