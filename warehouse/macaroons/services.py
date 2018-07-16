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

import pymacaroons

from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon as Macaroon


class InvalidMacaroon(Exception):
    ...


@implementer(IMacaroonService)
class DatabaseMacaroonService:
    def __init__(self, db_session):
        self.db = db_session

    def _get_record_from_db(self, macaroon):
        # TODO: Better handle parsing the identifier here.
        macaroon_id = macaroon.identifier.split()[1].split(b":")[1].decode("utf8")

        try:
            dm = (
                self.db.query(Macaroon)
                .options(joinedload("user"))
                .filter(Macaroon.id == macaroon_id)
                .one()
            )
        except NoResultFound:
            return

        return dm

    def find_userid(self, macaroon):
        m = pymacaroons.Macaroon.deserialize(macaroon)
        dm = self._get_record_from_db(m)

        return None if dm is None else dm.user.id

    def verify(self, macaroon):
        m = pymacaroons.Macaroon.deserialize(macaroon)
        dm = self._get_record_from_db(m)

        if dm is None:
            raise InvalidMacaroon

        verifier = pymacaroons.Verifier()

        if not verifier.verify(m, dm.key):
            raise InvalidMacaroon
        else:
            return True


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)
