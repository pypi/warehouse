# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord

from .base import WarehouseFactory
from .packaging import ReleaseFactory


class VulnerabilityRecordFactory(WarehouseFactory):
    class Meta:
        model = VulnerabilityRecord

    id = factory.Faker("word")
    source = factory.Faker("word")
    link = factory.Faker("uri")
    releases = factory.SubFactory(ReleaseFactory)
    details = factory.Faker("word")
