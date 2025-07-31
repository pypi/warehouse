# SPDX-License-Identifier: Apache-2.0

from warehouse.classifiers.models import Classifier

from .base import WarehouseFactory


class ClassifierFactory(WarehouseFactory):
    class Meta:
        model = Classifier
