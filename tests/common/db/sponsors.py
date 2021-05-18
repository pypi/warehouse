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

from factory import fuzzy

from warehouse.sponsors.models import Sponsor

from .base import FuzzyList, FuzzyUrl, WarehouseFactory


class SponsorFactory(WarehouseFactory):
    class Meta:
        model = Sponsor

    name = fuzzy.FuzzyText(length=12)
    service = fuzzy.FuzzyText(length=12)
    activity = FuzzyList(fuzzy.FuzzyText, {"length": 30}, size=2)

    link_url = FuzzyUrl()
    color_logo_url = FuzzyUrl()
    white_logo_url = FuzzyUrl()

    footer = True
    psf_sponsor = True
    infra_sponsor = False
    one_time = False
    sidebar = True
