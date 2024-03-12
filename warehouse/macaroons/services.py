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
from __future__ import annotations

import base64
import datetime
import uuid

from typing import TYPE_CHECKING

import pymacaroons

from pymacaroons.exceptions import MacaroonDeserializationException
from sqlalchemy.orm import joinedload
from zope.interface import implementer

if TYPE_CHECKING:
    from pyramid.request import Request

from warehouse.macaroons import caveats
from warehouse.macaroons.errors import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon
from warehouse.metrics import IMetricsService


def _extract_basic_macaroon(auth):
    """
    A helper function for extracting a macaroon from a
    HTTP Basic Authentication-style header.

    Returns None if the header doesn't contain a structurally
    valid macaroon, or the candidate (not yet verified) macaroon
    in a serialized form.
    """
    try:
        authorization = base64.b64decode(auth).decode()
        auth_method, _, auth = authorization.partition(":")
    except ValueError:
        return None

    if auth_method != "__token__":
        return None

    # Strip leading/trailing whitespace characters from the macaroon
    auth = auth.strip()

    return auth


def _extract_http_macaroon(request: Request, increase_metrics: bool = False):
    """
    A helper function for the extraction of HTTP Macaroon from a given request.
    Returns either a None if no macaroon could be found, or the string
    that represents our serialized macaroon.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    try:
        auth_method, auth = authorization.split(" ", 1)
    except ValueError:
        return None

    auth_method = auth_method.lower()

    if increase_metrics:
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment(
            "warehouse.macaroon.auth_method", tags=[f"method:{auth_method}"]
        )

    if auth_method == "basic":
        return _extract_basic_macaroon(auth)
    elif auth_method in ["token", "bearer"]:
        return auth

    return None


def _extract_raw_macaroon(prefixed_macaroon: str | None) -> str | None:
    """
    Returns the base64-encoded macaroon component of a PyPI macaroon,
    dropping the prefix.

    Returns None if the macaroon is None, has no prefix, or has the
    wrong prefix.
    """
    if prefixed_macaroon is None:
        return None

    prefix, _, raw_macaroon = prefixed_macaroon.partition("-")
    return None if prefix != "pypi" or not raw_macaroon else raw_macaroon


def deserialize_raw_macaroon(raw_macaroon: str | None) -> pymacaroons.Macaroon:
    """
    Returns a pymacaroons.Macaroon instance from a raw (serialized) macaroon.
    """
    raw_macaroon = _extract_raw_macaroon(raw_macaroon)

    if raw_macaroon is None:
        raise InvalidMacaroonError("malformed or nonexistent macaroon")

    try:
        return pymacaroons.Macaroon.deserialize(raw_macaroon)
    except (
        MacaroonDeserializationException,
        Exception,  # https://github.com/ecordell/pymacaroons/issues/50
    ) as e:
        raise InvalidMacaroonError("malformed macaroon") from e


@implementer(IMacaroonService)
class DatabaseMacaroonService:
    def __init__(self, db_session):
        self.db = db_session

    def find_macaroon(self, macaroon_id) -> Macaroon | None:
        """
        Returns a macaroon model from the DB by its identifier.
        Returns None if no macaroon has the given ID.
        """
        try:
            uuid.UUID(macaroon_id)
        except ValueError:
            return None

        return (
            self.db.query(Macaroon)
            .options(
                joinedload(Macaroon.user),
                joinedload(Macaroon.oidc_publisher),
            )
            .filter_by(id=macaroon_id)
            .one_or_none()
        )

    def find_userid(self, raw_macaroon: str) -> uuid.UUID | None:
        """
        Returns the id of the user associated with the given raw (serialized)
        macaroon.
        """
        try:
            m = deserialize_raw_macaroon(raw_macaroon)
        except InvalidMacaroonError:
            return None

        try:
            identifier = m.identifier.decode()
        except UnicodeDecodeError:
            return None

        dm = self.find_macaroon(identifier)

        if dm is None:
            return None

        # This can be None if the macaroon has no associated user
        # (e.g., an OIDC-minted macaroon).
        if dm.user is None:
            return None

        return dm.user.id

    def find_from_raw(self, raw_macaroon: str) -> Macaroon:
        """
        Returns a DB macaroon matching the input, or raises InvalidMacaroonError
        """
        m = deserialize_raw_macaroon(raw_macaroon)

        try:
            identifier = m.identifier.decode()
        except UnicodeDecodeError:
            raise InvalidMacaroonError("Macaroon not found")

        dm = self.find_macaroon(identifier)

        if not dm:
            raise InvalidMacaroonError("Macaroon not found")
        return dm

    def find_from_request(self, request: Request, increase_metrics: bool) -> Macaroon:
        """
        Returns a DB macaroon matching the input, or raises InvalidMacaroonError
        """
        # We need to extract our Macaroon from the request.
        macaroon = _extract_http_macaroon(request, increase_metrics)
        if macaroon is None:
            raise InvalidMacaroonError("Macaroon not found")

        return self.find_from_raw(macaroon)

    def verify(self, raw_macaroon: str, request, context, permission) -> bool:
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the request, context, and requested permission.

        Raises InvalidMacaroonError if the macaroon is not valid.
        """
        m = deserialize_raw_macaroon(raw_macaroon)
        dm = self.find_macaroon(m.identifier.decode())

        if dm is None:
            raise InvalidMacaroonError("deleted or nonexistent macaroon")

        verified = caveats.verify(m, dm.key, request, context, permission)
        if verified:
            dm.last_used = datetime.datetime.now()
            return True

        raise InvalidMacaroonError(verified.msg)

    def create_macaroon(
        self,
        location,
        description,
        scopes,
        *,
        user_id=None,
        oidc_publisher_id=None,
        additional=None,
    ):
        """
        Returns a tuple of a new raw (serialized) macaroon and its DB model.
        The description provided is not embedded into the macaroon, only stored
        in the DB model.

        An associated identity (either a user or macaroon, by ID) must be specified.
        """
        if not all(isinstance(c, caveats.Caveat) for c in scopes):
            raise TypeError("scopes must be a list of Caveat instances")

        # NOTE: This is a bit of a hack: we keep a separate copy of the
        # permissions caveat in the DB, so that we can display scope information
        # in the UI.
        permissions = {}
        for caveat in scopes:
            if isinstance(caveat, caveats.ProjectName):
                projects = permissions.setdefault("projects", [])
                projects.extend(caveat.normalized_names)
            elif isinstance(caveat, caveats.RequestUser):
                permissions = "user"
                break

        dm = Macaroon(
            user_id=user_id,
            oidc_publisher_id=oidc_publisher_id,
            description=description,
            permissions_caveat={"permissions": permissions},
            additional=additional,
            caveats=scopes,
        )
        self.db.add(dm)
        self.db.flush()  # flush db now so dm.id is available

        m = pymacaroons.Macaroon(
            location=location,
            identifier=str(dm.id),
            key=dm.key,
            version=pymacaroons.MACAROON_V2,
        )
        for caveat in scopes:
            m.add_first_party_caveat(caveats.serialize(caveat))
        serialized_macaroon = f"pypi-{m.serialize()}"
        return serialized_macaroon, dm

    def delete_macaroon(self, macaroon_id) -> None:
        """
        Deletes a macaroon from the DB by its identifier.
        """
        dm = self.find_macaroon(macaroon_id)
        self.db.delete(dm) if dm else None

    def get_macaroon_by_description(self, user_id, description):
        """
        Returns a macaroon model from the DB with the given description,
        if one exists for the given user.

        Returns None if the user doesn't have a macaroon with this description.
        """
        dm = (
            self.db.query(Macaroon)
            .filter(Macaroon.description == description)
            .filter(Macaroon.user_id == user_id)
            .one_or_none()
        )

        return dm


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)
