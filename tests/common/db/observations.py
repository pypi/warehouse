# SPDX-License-Identifier: Apache-2.0

from warehouse.observations.models import Observer

from .base import WarehouseFactory


class ObserverFactory(WarehouseFactory):
    class Meta:
        model = Observer
