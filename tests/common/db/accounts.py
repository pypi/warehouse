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
import faker

from argon2 import PasswordHasher

from warehouse.accounts.models import (
    Email,
    ProhibitedEmailDomain,
    ProhibitedUserName,
    TermsOfServiceEngagement,
    User,
    UserTermsOfServiceEngagement,
)

from .base import WarehouseFactory

fake = faker.Faker()


class UserFactory(WarehouseFactory):
    class Meta:
        model = User

    class Params:
        # Shortcut to create a user with a verified primary email
        with_verified_primary_email = factory.Trait(
            email=factory.RelatedFactory(
                "tests.common.db.accounts.EmailFactory",
                factory_related_name="user",
                primary=True,
                verified=True,
            )
        )
        # Shortcut to create a user with a ToS Agreement
        with_terms_of_service_agreement = factory.Trait(
            terms_of_service_engagements=factory.RelatedFactory(
                "tests.common.db.accounts.UserTermsOfServiceEngagementFactory",
                factory_related_name="user",
            )
        )
        # Allow passing a cleartext password to the factory
        # This will be hashed before saving the user.
        # Usage: UserFactory(clear_pwd="password")
        clear_pwd = None

    username = factory.Faker("pystr", max_chars=12)
    name = factory.Faker("word")
    password = factory.LazyAttribute(
        # Note: argon2 is used directly here, since it's our "best" hashing algorithm
        # instead of using `passlib`, since we may wish to replace it.
        lambda obj: (
            PasswordHasher(
                memory_cost=1024,
                parallelism=6,
                time_cost=6,
            ).hash(obj.clear_pwd)
            if obj.clear_pwd
            else "!"
        )
    )
    is_active = True
    is_superuser = False
    is_moderator = False
    is_psf_staff = False
    date_joined = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2005, 1, 1),
        datetime_end=datetime.datetime(2010, 1, 1),
    )
    last_login = factory.Faker(
        "date_time_between_dates", datetime_start=datetime.datetime(2011, 1, 1)
    )
    totp_secret = factory.Faker("binary", length=20)


class UserEventFactory(WarehouseFactory):
    class Meta:
        model = User.Event

    source = factory.SubFactory(User)


class UserTermsOfServiceEngagementFactory(WarehouseFactory):
    class Meta:
        model = UserTermsOfServiceEngagement

    revision = "initial"
    engagement = TermsOfServiceEngagement.Agreed
    created = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2025, 1, 1),
        datetime_end=datetime.datetime(2025, 2, 19),
    )


class EmailFactory(WarehouseFactory):
    class Meta:
        model = Email

    user = factory.SubFactory(UserFactory)

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    email = factory.Sequence(lambda _: fake.unique.safe_email())

    verified = True
    primary = True
    public = False
    unverify_reason = None
    transient_bounces = 0


class ProhibitedEmailDomainFactory(WarehouseFactory):
    class Meta:
        model = ProhibitedEmailDomain

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    domain = factory.Sequence(lambda _: fake.unique.domain_name())


class ProhibitedUsernameFactory(WarehouseFactory):
    class Meta:
        model = ProhibitedUserName

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    name = factory.Sequence(lambda _: fake.unique.user_name())
