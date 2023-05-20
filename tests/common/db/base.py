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
