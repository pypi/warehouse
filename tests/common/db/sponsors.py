# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.sponsors.models import Sponsor

from .base import WarehouseFactory


class SponsorFactory(WarehouseFactory):
    class Meta:
        model = Sponsor

    name = factory.Faker("word")
    service = factory.Faker("sentence")
    activity_markdown = factory.Faker("sentence")

    link_url = factory.Faker("uri")
    color_logo_url = factory.Faker("image_url")
    white_logo_url = factory.Faker("image_url")

    is_active = True
    footer = True
    psf_sponsor = True
    infra_sponsor = False
    one_time = False
    sidebar = True

    origin = "manual"
    level_name = ""
    level_order = 0
    slug = factory.Faker("slug")
