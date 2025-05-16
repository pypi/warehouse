# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.banners.models import Banner

from .base import WarehouseFactory


class BannerFactory(WarehouseFactory):
    class Meta:
        model = Banner

    name = factory.Faker("word")
    text = factory.Faker("sentence")
    link_url = factory.Faker("uri")
    link_label = factory.Faker("word")

    active = True
    end = factory.Faker("future_date")
