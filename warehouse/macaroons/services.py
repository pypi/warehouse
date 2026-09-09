# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import dataclasses
import datetime
import typing
import uuid

from collections.abc import Iterator

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


# Packet field types of the v2 macaroon format, which is a stream of
# `field_type, length, payload` packets, both numbers LEB128 varints, with a
# zero byte ending each section: the header, then one section per caveat, then
# the signature.
# https://github.com/rescrv/libmacaroons/blob/master/doc/format.txt
_PACKET_EOS = 0
_PACKET_LOCATION = 1
_PACKET_IDENTIFIER = 2
_PACKET_SIGNATURE = 6

# Three varint bytes already span 21 bits, well past any length a real packet
# declares. Reading further only builds an integer too large to render.
_MAX_VARINT_BYTES = 3

# A token scoped to many projects names each one in a caveat, so leave room
# for a few kilobytes of them. Past this a paste is not a macaroon.
_MAX_TOKEN_BYTES = 16 * 1024


@dataclasses.dataclass(frozen=True)
class _Packet:
    """
    One packet of a v2 macaroon. A packet cut short has a `payload` shorter
    than its `declared_length`.
    """

    field_type: int
    payload: bytes
    declared_length: int

    @property
    def complete(self) -> bool:
        return len(self.payload) == self.declared_length


@dataclasses.dataclass
class PartialMacaroon:
    """
    The fields recovered from a macaroon that will not fully deserialize, as
    display strings. A field cut short carries a note of its declared length.
    """

    location: str | None = None
    identifier: str | None = None
    identifier_complete: bool = False
    """Whether the identifier was read whole, so it can be looked up."""

    caveats: list[str] = dataclasses.field(default_factory=list)
    signature: str | None = None


def _b64_prefix_decode(raw_macaroon: str) -> bytes:
    """
    Decode a base64url string that may have been cut mid-quantum, keeping the
    bytes its final partial quantum still encodes. Returns b"" if even that
    cannot be decoded, as when the string holds a non-ASCII character such as
    an elision ellipsis.
    """
    # A paste carries whitespace that b64decode would drop anyway, and that
    # would throw off the quantum arithmetic below if left in.
    body = "".join(raw_macaroon.split())
    # A lone trailing character encodes no whole byte.
    body = body[:-1] if len(body) % 4 == 1 else body
    try:
        return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except ValueError:
        return b""


def _read_uvarint(data: bytes, index: int) -> tuple[int, int]:
    """
    Read the LEB128 varint at `index`, returning it and the index after it.
    Raises ValueError if `data` ends mid-varint, or if the varint runs on
    longer than a packet field ever needs.
    """
    value = 0
    for shift in range(0, 7 * _MAX_VARINT_BYTES, 7):
        if index >= len(data):
            raise ValueError("varint cut short")
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
    raise ValueError("varint too long for a packet field")


def _read_packets(data: bytes) -> Iterator[_Packet]:
    """
    Yield the packets of a v2 macaroon body, stopping once `data` runs out
    rather than rejecting the macaroon as a whole. A packet whose payload was
    cut short is yielded last: its declared length takes the index past the
    end of `data`.

    Field types climb within a section, so a repeated or out of order field
    ends the read. Without that rule a second identifier packet would speak
    over the first, and a caveat in a stream that never ends its header would
    be read as the identifier.
    """
    index = 0
    previous_field_type = _PACKET_EOS
    while index < len(data):
        try:
            field_type, index = _read_uvarint(data, index)
            if field_type == _PACKET_EOS:
                previous_field_type = _PACKET_EOS
                yield _Packet(field_type, b"", 0)
                continue
            if field_type <= previous_field_type:
                return
            previous_field_type = field_type
            declared_length, index = _read_uvarint(data, index)
        except ValueError:
            return
        payload = data[index : index + declared_length]
        index += declared_length
        yield _Packet(field_type, payload, declared_length)


def _packet_text(packet: _Packet) -> str:
    """Render a packet's payload for display, with a note if it was cut short."""
    if packet.field_type == _PACKET_SIGNATURE:
        text = packet.payload.hex()
    else:
        try:
            text = packet.payload.decode()
        except UnicodeDecodeError:
            text = packet.payload.hex()

    if not packet.complete:
        note = f"(truncated, {packet.declared_length} bytes declared)"
        return f"{text} {note}" if text else note
    return text


def deserialize_partial_macaroon(
    prefixed_macaroon: str | None,
) -> PartialMacaroon | None:
    """
    Returns whatever fields can still be read out of a PyPI macaroon that
    `deserialize_raw_macaroon` rejects, usually one that was truncated.

    Returns None if nothing could be read, including anything that is not a
    v2 macaroon.
    """
    raw_macaroon = _extract_raw_macaroon(prefixed_macaroon)
    if raw_macaroon is None:
        return None

    data = _b64_prefix_decode(raw_macaroon)
    if not data or len(data) > _MAX_TOKEN_BYTES or data[0] != pymacaroons.MACAROON_V2:
        return None

    partial = PartialMacaroon()
    in_header = True
    for packet in _read_packets(data[1:]):
        # A caveat's own location and verification key id are ignored: PyPI
        # only issues first party caveats, which have neither.
        if packet.field_type == _PACKET_EOS:
            in_header = False
        elif packet.field_type == _PACKET_SIGNATURE:
            partial.signature = _packet_text(packet)
        elif packet.field_type == _PACKET_LOCATION and in_header:
            partial.location = _packet_text(packet)
        elif packet.field_type == _PACKET_IDENTIFIER:
            if in_header:
                try:
                    packet.payload.decode()
                except UnicodeDecodeError:
                    # `uuid.UUID` would take the hex we would render this
                    # as, naming a macaroon the token itself cannot name.
                    return None
                partial.identifier = _packet_text(packet)
                partial.identifier_complete = packet.complete
            else:
                partial.caveats.append(_packet_text(packet))

    return partial if partial != PartialMacaroon() else None


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
