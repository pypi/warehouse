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

from factory.alchemy import SQLAlchemyModelFactory

from . import Session


class WarehouseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = Session

    @classmethod
    def _setup_next_sequence(cls, *args, **kwargs):
        return 0

    @classmethod
    def _create(cls, *args, **kwargs):
        r = super()._create(*args, **kwargs)
        session = cls._meta.sqlalchemy_session
        session.flush()
        session.expire_all()
        return r


class UniqueFaker(factory.Faker):
    """A Faker class that produces unique values.
    This is needed because sometimes a non-unique Faker produces duplicate values,
    which can cause tests to fail inconsistently."""

    def evaluate(self, instance, step, extra):
        # Note: this implementation does not clear the faker 'unique cache',
        # which means that there may be no unique values remaining,
        # or not enough to find a new value in a reasonable time.
        # This situation will throw UniquenessException.
        locale = extra.pop("locale")
        subfaker = self._get_faker(locale)
        unique_proxy = subfaker.unique
        return unique_proxy.format(self.provider, **extra)
