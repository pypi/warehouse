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

from warehouse.accounts.models import User
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon


class InvalidMacaroon(Exception):
    ...


@implementer(IMacaroonService)
class DatabaseMacaroonService:
    def __init__(self, db_session):
        self.db = db_session

    def find_macaroon(self, macaroon_id):
        try:
            version, identifier = macaroon_id.split(".", 1)
        except ValueError:
            return None

        if version != "v1":
            return None

        try:
            dm = (
                self.db.query(Macaroon)
                .options(joinedload("user"))
                .filter(Macaroon.id == identifier)
                .one()
            )
        except NoResultFound:
            return None

        return dm

    def find_userid(self, macaroon):
        if macaroon is None:
            return None
        m = pymacaroons.Macaroon.deserialize(macaroon)
        dm = self.find_macaroon(m.identifier)

        return None if dm is None else dm.user.id

    def verify(self, macaroon, context, principals, permission):
        m = pymacaroons.Macaroon.deserialize(macaroon)
        dm = self.find_macaroon(m.identifier)

        if dm is None:
            raise InvalidMacaroon

        verifier = pymacaroons.Verifier()

        if not verifier.verify(m, dm.key):
            raise InvalidMacaroon
        else:
            return True

    def create_macaroon(self, location, user_id, description, caveats):
        user = self.db.query(User).filter(User.id == user_id).one()

        dm = Macaroon(user=user, description=description, caveats=caveats)
        self.db.add(dm)
        self.db.flush()

        m = pymacaroons.Macaroon(
            location=location, identifier=dm.identifier, key=dm.key
        )
        return m.serialize()

    def delete_macaroon(self, macaroon_id):
        dm = self.find_macaroon(macaroon_id)
        self.db.delete(dm)
        self.db.flush()


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)
