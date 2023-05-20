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
