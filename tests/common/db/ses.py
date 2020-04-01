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

import factory
import factory.fuzzy

from warehouse.email.ses.models import EmailMessage, Event, EventTypes

from .base import FuzzyEmail, WarehouseFactory


class EmailMessageFactory(WarehouseFactory):
    class Meta:
        model = EmailMessage

    created = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime.utcnow() - datetime.timedelta(days=14)
    )
    message_id = factory.fuzzy.FuzzyText(length=12)
    from_ = FuzzyEmail()
    to = FuzzyEmail()
    subject = factory.fuzzy.FuzzyText(length=100)


class EventFactory(WarehouseFactory):
    class Meta:
        model = Event

    created = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime.utcnow() - datetime.timedelta(days=14)
    )
    email = factory.SubFactory(EmailMessageFactory)
    event_id = factory.fuzzy.FuzzyText(length=12)
    event_type = factory.fuzzy.FuzzyChoice([e.value for e in EventTypes])
