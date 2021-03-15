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
import os
import uuid

import pypitoken

from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.models import User
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon


def _generate_key():
    return os.urandom(32)


class InvalidMacaroonError(Exception):
    ...


TOKEN_PREFIX = "pypi"


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
                .filter(Macaroon.id == uuid.UUID(macaroon_id))
                .one()
            )
        except NoResultFound:
            return None

        return dm

    def _deserialize_raw_macaroon(self, raw_macaroon):
        try:
            token = pypitoken.Token.load(raw_macaroon)
        except pypitoken.LoaderError as exc:
            raise InvalidMacaroonError(str(exc))
        if token.prefix != TOKEN_PREFIX:
            raise InvalidMacaroonError(
                f"Token has wrong prefix: {token.prefix} (expected {TOKEN_PREFIX}"
            )
        # We don't check the domain because it's checks as part of the signature check
        return token

    def find_userid(self, raw_macaroon):
        """
        Returns the id of the user associated with the given raw (serialized)
        macaroon or None.
        """
        try:
            dm = self.find_from_raw(raw_macaroon)
        except InvalidMacaroonError:
            return None

        return dm.user.id

    def find_from_raw(self, raw_macaroon):
        """
        Returns a DB macaroon matching the imput, or raises InvalidMacaroonError
        """
        m = self._deserialize_raw_macaroon(raw_macaroon)
        dm = self.find_macaroon(m.identifier)
        if not dm:
            raise InvalidMacaroonError("Macaroon not found")
        return dm

    def verify(self, raw_macaroon, context, principals, permission):
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the context, principals, and requested permission.

        Raises InvalidMacaroonError if the macaroon is not valid.
        """
        token = self._deserialize_raw_macaroon(raw_macaroon)
        dm = self.find_macaroon(token.identifier)

        if dm is None:
            raise InvalidMacaroonError("deleted or nonexistent macaroon")

        project = context.normalized_name

        try:
            token.check(key=dm.key, project=project)
        except pypitoken.ValidationError as exc:
            raise InvalidMacaroonError(str(exc))

        dm.last_used = datetime.datetime.now()
        return True

    def create_macaroon(self, domain, user_id, description, restrictions):
        """
        Returns a tuple of a new raw (serialized) macaroon and its DB model.
        The description provided is not embedded into the macaroon, only stored
        in the DB model.
        """
        user = self.db.query(User).filter(User.id == user_id).one()

        identifier = uuid.uuid4()
        key = _generate_key()

        token = pypitoken.Token.create(
            domain=domain, identifier=str(identifier), key=key, prefix="pypi"
        )
        # even if projects is None, this will create a NoopRestriction. With
        # the current implementation, we need to always have a restriction in place.
        token.restrict(
            # We're likely to copy restrictions into this function kwargs as-is, but
            # it's good to avoid **restrictions here to maintain the abstraction layer.
            # If something break because the pypitoken lib expects new arguments, we'd
            # rather it fails here and be sure to see it in the tests.
            projects=restrictions.get("projects", None),
        )

        dm = Macaroon(
            id=identifier,
            user=user,
            key=key,
            description=description,
            caveats=token.restrictions[0].dump(),
        )
        self.db.add(dm)
        self.db.flush()

        return token.dump(), dm

    def describe_caveats(self, caveats):
        description = {}
        restriction = pypitoken.Restriction.load(caveats)

        if isinstance(restriction, pypitoken.ProjectsRestriction):
            description["projects"] = restriction.projects

        return description

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
