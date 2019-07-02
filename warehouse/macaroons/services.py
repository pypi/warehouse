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

import json

import pymacaroons

from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.models import User
from warehouse.macaroons.caveats import Verifier
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon


class InvalidMacaroon(Exception):
    ...


@implementer(IMacaroonService)
class DatabaseMacaroonService:
    def __init__(self, db_session):
        self.db = db_session

    def find_macaroon(self, macaroon_id):
        """
        Returns a macaroon model from the DB by its identifier.
        Returns None if no macaroon has the given ID.
        """
        try:
            dm = (
                self.db.query(Macaroon)
                .options(joinedload("user"))
                .filter(Macaroon.id == macaroon_id)
                .one()
            )
        except NoResultFound:
            return None

        return dm

    def find_userid(self, raw_macaroon):
        """
        Returns the id of the user associated with the given raw (serialized)
        macaroon.
        """
        if raw_macaroon is None:
            return None
        m = pymacaroons.Macaroon.deserialize(raw_macaroon)
        dm = self.find_macaroon(m.identifier)

        if dm is None:
            return None

        return dm.user.id

    def verify(self, raw_macaroon, context, principals, permission):
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the context, principals, and requested permission.

        Raises InvalidMacaroon if the macaroon is not valid.
        """
        m = pymacaroons.Macaroon.deserialize(raw_macaroon)
        dm = self.find_macaroon(m.identifier)

        if dm is None:
            raise InvalidMacaroon

        verifier = Verifier(m, context, principals, permission)
        if not verifier.verify(dm.key):
            raise InvalidMacaroon
        else:
            return True

    def create_macaroon(self, location, user_id, description, caveats):
        """
        Returns a new raw (serialized) macaroon. The description provided
        is not embedded into the macaroon, only stored in the DB model.
        """
        user = self.db.query(User).filter(User.id == user_id).one()

        dm = Macaroon(user=user, description=description, caveats=caveats)
        self.db.add(dm)
        self.db.flush()

        m = pymacaroons.Macaroon(
            location=location,
            identifier=str(dm.id),
            key=dm.key,
            version=pymacaroons.MACAROON_V2,
        )
        m.add_first_party_caveat(json.dumps(caveats))
        return m.serialize()

    def delete_macaroon(self, macaroon_id):
        """
        Deletes a macaroon from the DB by its identifier.
        """
        dm = self.find_macaroon(macaroon_id)
        self.db.delete(dm)
        self.db.flush()


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)
