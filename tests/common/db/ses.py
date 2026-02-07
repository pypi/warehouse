# SPDX-License-Identifier: Apache-2.0

import datetime

import factory
import faker

from warehouse.email.ses.models import EmailMessage, Event, EventTypes

from .base import WarehouseFactory

fake = faker.Faker()


class EmailMessageFactory(WarehouseFactory):
    class Meta:
        model = EmailMessage

    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime.now(datetime.UTC)
        - datetime.timedelta(days=14),
    )
    message_id = factory.Faker("pystr", max_chars=12)

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    from_ = factory.Sequence(lambda _: fake.unique.safe_email())
    to = factory.Sequence(lambda _: fake.unique.safe_email())

    subject = factory.Faker("sentence")


class EventFactory(WarehouseFactory):
    class Meta:
        model = Event

    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime.now(datetime.UTC)
        - datetime.timedelta(days=14),
    )
    email = factory.SubFactory(EmailMessageFactory)
    event_id = factory.Faker("pystr", max_chars=12)
    event_type = factory.Faker("random_element", elements=[e.value for e in EventTypes])
