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
import factory.fuzzy

from warehouse.classifiers.models import Classifier

from .base import WarehouseFactory


class ClassifierFactory(WarehouseFactory):
    class Meta(object):
        model = Classifier

    l2 = factory.fuzzy.FuzzyInteger(0)
    l3 = factory.fuzzy.FuzzyInteger(0)
    l4 = factory.fuzzy.FuzzyInteger(0)
    l5 = factory.fuzzy.FuzzyInteger(0)
