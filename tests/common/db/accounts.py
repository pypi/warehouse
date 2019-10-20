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

from warehouse.accounts.models import Email, User, UserEvent

from .base import FuzzyEmail, WarehouseFactory


class UserFactory(WarehouseFactory):
    class Meta:
        model = User

    username = factory.fuzzy.FuzzyText(length=12)
    name = factory.fuzzy.FuzzyText(length=12)
    password = "!"
    is_active = True
    is_superuser = False
    is_moderator = False
    date_joined = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime(2005, 1, 1), datetime.datetime(2010, 1, 1)
    )
    last_login = factory.fuzzy.FuzzyNaiveDateTime(datetime.datetime(2011, 1, 1))
    is_email_private = True


class UserEventFactory(WarehouseFactory):
    class Meta:
        model = UserEvent

    user = factory.SubFactory(User)


class EmailFactory(WarehouseFactory):
    class Meta:
        model = Email

    user = factory.SubFactory(UserFactory)
    email = FuzzyEmail()
    verified = True
    primary = True
    unverify_reason = None
    transient_bounces = 0
