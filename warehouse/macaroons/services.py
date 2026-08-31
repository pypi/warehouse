# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import typing
import uuid

import pymacaroons

from pymacaroons.exceptions import MacaroonDeserializationException
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from zope.interface import implementer

from warehouse.macaroons import caveats
from warehouse.macaroons.errors import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.models import Macaroon

if typing.TYPE_CHECKING:
    from pyramid.request import Request


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


def _decode_identifier(macaroon: pymacaroons.Macaroon) -> str:
    """Return a macaroon's UTF-8 identifier or raise InvalidMacaroonError."""
    try:
        return macaroon.identifier.decode()
    except UnicodeDecodeError as e:
        raise InvalidMacaroonError("malformed macaroon identifier") from e


def _record_attenuations(request: Request, extra: list[str] | None) -> None:
    """
    Record how a verified macaroon was attenuated, as `attenuated:<state>` on
    `warehouse.macaroon.verify.attenuated`. `extra` is the result of
    `caveats.attenuations()`, or None if there was nothing to compare against.

    The states are:

    * `unknown`: we have no stored caveats for this macaroon, so we cannot tell
      which of its embedded caveats are ours. Only macaroons created before we
      started storing our caveats in the database land here, so this bucket
      should shrink over time as those tokens are replaced.
    * `false`: every embedded caveat is one that we issued. This is what a token
      we minted looks like when the user hasn't touched it.
    * `true`: the macaroon carries caveats that we did not issue, so someone
      restricted it further after we handed it over. Each kind is counted on
      `warehouse.macaroon.verify.attenuation_kind`, where "unknown" means a
      caveat we could not deserialize at all rather than a `Caveat` subclass.

    Only macaroons that passed verification are recorded, so these counts
    describe tokens in real use rather than anything an anonymous caller can
    present.
    """
    if extra is None:
        request.metrics.increment(
            "warehouse.macaroon.verify.attenuated", tags=["attenuated:unknown"]
        )
        return

    request.metrics.increment(
        "warehouse.macaroon.verify.attenuated",
        tags=[f"attenuated:{'true' if extra else 'false'}"],
    )
    for kind in sorted(set(extra)):
        request.metrics.increment(
            "warehouse.macaroon.verify.attenuation_kind", tags=[f"caveat:{kind}"]
        )


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
            identifier = _decode_identifier(m)
        except InvalidMacaroonError:
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
        dm = self.find_macaroon(_decode_identifier(m))

        if not dm:
            raise InvalidMacaroonError("Macaroon not found")
        return dm

    def verify(self, raw_macaroon: str, request, context, permission) -> bool:
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the request, context, and requested permission.

        Raises InvalidMacaroonError if the macaroon is not valid.
        """
        m = deserialize_raw_macaroon(raw_macaroon)
        dm = self.find_macaroon(_decode_identifier(m))

        if dm is None:
            raise InvalidMacaroonError("deleted or nonexistent macaroon")

        issued = dm.caveats

        # Work out which caveats the end user added themselves before we append our
        # own stored caveats below, which would make the two indistinguishable. We
        # don't record this until we know the macaroon verifies, so that anyone who
        # reads an identifier out of a token can't skew the numbers with forgeries.
        attenuations = caveats.attenuations(m, issued) if issued else None

        # Macaroons traditionally have caveats embedded inside them which act to
        # restrict the scope of what that macaroon is able to do. However, each caveat
        # that is added has to be serialized into the Macaroon which makes them longer
        # the more restricted they become.
        #
        # In the common case, end users often don't add their own caveats to the
        # macaroons we give them, the only caveats that exist are the ones that were
        # added by Warehouse when the macaroons was first created. This allows end users
        # to introspect the macaroon without having to talk to PyPI, but means that they
        # are already longer than is typical for an API token out of the gate.
        #
        # Relying strictly on the embedded caveats also makes it more difficult to
        # evolve the use cases that the token system is able to handle over time when
        # assumptions that used to be made can no longer be assumed (such as they're
        # only used for uploads and then wanting to use them for other use cases).
        #
        # To solve this, what we do is we allow storing caveats in the database in
        # addition to the embedded caveats, and when verifying the macaroon we append
        # those caveats to the end of the macaroon.
        #
        # This means:
        #  1. The system generated caveats do not need to be embedded, because they are
        #     in the database and dynamically added at verify time.
        #  2. We can add new caveats to any existing macaroon by adding the caveat to
        #     the stored caveats in the database.
        #  3. When the macaroon has the system generated caveats embedded, appending
        #     them is harmless (other than a small cpu cost) because it's just verifying
        #     the same restrictions twice.
        #
        # NOTE: We choose to mutate the macaroon that was given to us by appending the
        #       stored caveats to the end of it. This is safe and means that the caveat
        #       verification code doesn't have to do anything special for stored vs
        #       embedded caveats. However, it does mean that the macaroon we actually
        #       end up verifying is a "sub" macaroon of what the user provided us.
        for caveat in issued:
            m.add_first_party_caveat(caveats.serialize(caveat))

        verified = caveats.verify(m, dm.key, request, context, permission)
        if verified:
            _record_attenuations(request, attenuations)

            # Update last_used without dirtying the ORM object. A dirty
            # macaroon causes autoflush during Project.__acl__() evaluation,
            # which can deadlock with the journal advisory lock under
            # concurrent uploads. SKIP LOCKED ensures that if another
            # transaction is already updating this row (same token used
            # concurrently), we just skip — the other transaction will
            # set last_used anyway.
            # skipping is okay as last_used value is imprecise (python dt, not DB clock)
            # and informational in the ui
            self.db.execute(
                update(Macaroon)
                .where(
                    Macaroon.id.in_(
                        select(Macaroon.id)
                        .where(Macaroon.id == dm.id)
                        .with_for_update(skip_locked=True)
                    )
                )
                .values(last_used=datetime.datetime.now())
            )

            return True

        raise InvalidMacaroonError(verified.msg)

    def verify_signature_only(self, raw_macaroon: str) -> Macaroon:
        """
        Returns a macaroon model from the DB if the given raw (serialized)
        macaroon exists and has a valid signature.

        **NOTE**: this API is not a substitute for `verify`; most
        users should call `verify` to validate both the signature
        *and* the macaroon's caveats relative to the request.

        Raises InvalidMacaroonError if the macaroon has an invalid
        signature.
        """

        m = deserialize_raw_macaroon(raw_macaroon)
        dm = self.find_macaroon(_decode_identifier(m))

        if not dm:
            raise InvalidMacaroonError("Macaroon not found")

        try:
            verifier = pymacaroons.Verifier()
            # Satisfy every caveat trivially, so that they get incorporated
            # into the signature check.
            verifier.satisfy_general(lambda _: True)
            verifier.verify(m, dm.key)
            return dm
        except (
            pymacaroons.exceptions.MacaroonInvalidSignatureException,
            Exception,  # noqa: BLE001 https://github.com/ecordell/pymacaroons/issues/50
        ):
            raise InvalidMacaroonError("Invalid signature")

    def create_macaroon(
        self,
        location: str,
        description: str,
        scopes: list[caveats.Caveat],
        *,
        user_id: uuid.UUID | None = None,
        oidc_publisher_id: str | None = None,
        additional: dict[str, typing.Any] | None = None,
    ) -> tuple[str, Macaroon]:
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
        permissions: dict[str, list[str]] | str = {}
        for caveat in scopes:
            if isinstance(caveat, caveats.ProjectName):
                permissions = typing.cast(dict[str, list[str]], permissions)
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
        self.db.flush()  # generate dm.id   # ast-grep-ignore: db-flush

        m = pymacaroons.Macaroon(
            location=location,
            identifier=str(dm.id),
            key=dm.key,
            version=pymacaroons.MACAROON_V2,
        )
        # TODO: Remove this to stop emitting embedded caveats, which are now
        #       being stored in the database while still being verified.
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
        return (
            self.db.query(Macaroon)
            .filter(Macaroon.description == description)
            .filter(Macaroon.user_id == user_id)
            .one_or_none()
        )


def database_macaroon_factory(context, request):
    return DatabaseMacaroonService(request.db)
