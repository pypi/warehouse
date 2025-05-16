# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.admin.flags import AdminFlag

from .base import WarehouseFactory


class AdminFlagFactory(WarehouseFactory):
    class Meta:
        model = AdminFlag

    id = factory.Faker("text", max_nb_chars=12)
    description = factory.Faker("sentence")
    enabled = True
