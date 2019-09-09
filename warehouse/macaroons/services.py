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
import json
import uuid

import pymacaroons

from pymacaroons.exceptions import MacaroonDeserializationException
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.models import User
from warehouse.macaroons.caveats import InvalidMacaroon, Verifier
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon


@implementer(IMacaroonService)
class DatabaseMacaroonService:
    def __init__(self, db_session):
        self.db = db_session

    def _extract_raw_macaroon(self, prefixed_macaroon):
        """
        Returns the base64-encoded macaroon component of a PyPI macaroon,
        dropping the prefix.

        Returns None if the macaroon is None, has no prefix, or has the
        wrong prefix.
        """
        if prefixed_macaroon is None:
            return None

        prefix, _, raw_macaroon = prefixed_macaroon.partition("-")
        if prefix != "pypi" or not raw_macaroon:
            return None

        return raw_macaroon

    def find_macaroon(self, macaroon_id):
        """
        Returns a macaroon model from the DB by its identifier.
        Returns None if no macaroon has the given ID.
        """
        try:
            dm = (
                self.db.query(Macaroon)
                .options(joinedload("user"))
                .filter(Macaroon.id == uuid.UUID(macaroon_id))
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
        raw_macaroon = self._extract_raw_macaroon(raw_macaroon)
        if raw_macaroon is None:
            return None

        try:
            m = pymacaroons.Macaroon.deserialize(raw_macaroon)
        except MacaroonDeserializationException:
            return None

        dm = self.find_macaroon(m.identifier.decode())

        if dm is None:
            return None

        return dm.user.id

    def verify(self, raw_macaroon, context, principals, permission):
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the context, principals, and requested permission.

        Raises InvalidMacaroon if the macaroon is not valid.
        """
        raw_macaroon = self._extract_raw_macaroon(raw_macaroon)
        if raw_macaroon is None:
            raise InvalidMacaroon("malformed or nonexistent macaroon")

        try:
            m = pymacaroons.Macaroon.deserialize(raw_macaroon)
        except MacaroonDeserializationException:
            raise InvalidMacaroon("malformed macaroon")

        dm = self.find_macaroon(m.identifier.decode())

        if dm is None:
            raise InvalidMacaroon("deleted or nonexistent macaroon")

        verifier = Verifier(m, context, principals, permission)
        if verifier.verify(dm.key):
            dm.last_used = datetime.datetime.now()
            return True

        raise InvalidMacaroon("invalid macaroon")

    def create_macaroon(self, location, user_id, description, caveats):
        """
        Returns a tuple of a new raw (serialized) macaroon and its DB model.
        The description provided is not embedded into the macaroon, only stored
        in the DB model.
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
        serialized_macaroon = f"pypi-{m.serialize()}"
        return serialized_macaroon, dm

    def delete_macaroon(self, macaroon_id):
        """
        Deletes a macaroon from the DB by its identifier.
        """
        dm = self.find_macaroon(macaroon_id)
        self.db.delete(dm)
        self.db.flush()

    def get_macaroon_by_description(self, user_id, description):
        """
        Returns a macaroon model from the DB with the given description,
        if one exists for the given user.

        Returns None if the user doesn't have a macaroon with this description.
        """
        try:
            dm = (
                self.db.query(Macaroon)
                .options(joinedload("user"))
                .filter(Macaroon.description == description)
                .filter(Macaroon.user_id == user_id)
                .one()
            )
        except NoResultFound:
            return None

        return dm


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)