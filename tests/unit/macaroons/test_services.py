# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import struct

from uuid import uuid4

import pymacaroons
import pytest

from pymacaroons.exceptions import MacaroonDeserializationException
from pymacaroons.serializers.binary_serializer import BinarySerializer

from warehouse.errors import WarehouseDenied
from warehouse.macaroons import caveats, services
from warehouse.macaroons.models import Macaroon

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory


def test_database_macaroon_factory(db_request):
    service = services.database_macaroon_factory(None, db_request)
    assert service.db is db_request.db


class TestDatabaseMacaroonService:
    def test_creation(self, mocker):
        session = mocker.sentinel.session
        service = services.DatabaseMacaroonService(session)

        assert service.db is session

    @pytest.mark.parametrize(
        ("raw_macaroon", "result"),
        [
            (None, None),
            ("noprefixhere", None),
            ("invalid:prefix", None),
            ("pypi-validprefix", "validprefix"),
        ],
    )
    def test_extract_raw_macaroon(self, raw_macaroon, result):
        assert services._extract_raw_macaroon(raw_macaroon) == result

    def test_find_macaroon_invalid_uuid(self, macaroon_service):
        assert macaroon_service.find_macaroon("foobar") is None

    def test_find_macaroon_missing_macaroon(self, macaroon_service):
        assert macaroon_service.find_macaroon(str(uuid4())) is None

    def test_find_macaroon(self, user_service, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

        dm = macaroon_service.find_macaroon(str(macaroon.id))

        assert isinstance(dm, Macaroon)
        assert macaroon.id == dm.id
        assert macaroon.user == user

    def test_find_from_raw(self, user_service, macaroon_service):
        user = UserFactory.create()
        serialized, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

        dm = macaroon_service.find_from_raw(serialized)

        assert isinstance(dm, Macaroon)
        assert macaroon.id == dm.id
        assert macaroon.user == user
        assert macaroon.additional is None

    def test_find_from_raw_oidc(self, macaroon_service):
        publisher = GitHubPublisherFactory.create()
        claims = {"sha": "somesha", "ref": "someref"}
        (
            serialized,
            macaroon,
        ) = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id))],
            oidc_publisher_id=publisher.id,
            additional=claims,
        )

        dm = macaroon_service.find_from_raw(serialized)

        assert isinstance(dm, Macaroon)
        assert macaroon.id == dm.id
        assert macaroon.oidc_publisher == publisher
        assert macaroon.additional == claims

    @pytest.mark.parametrize(
        "raw_macaroon",
        [
            "pypi-aaaa",  # Invalid macaroon
            # Macaroon properly formatted but not found.
            # The string is purposely cut to avoid triggering the github token
            # disclosure feature that this very function implements.
            "py"
            "pi-AgEIcHlwaS5vcmcCJGQ0ZDhhNzA2LTUxYTEtNDg0NC1hNDlmLTEyZDRiYzNkYjZmOQAABi"
            "D6hJOpYl9jFI4jBPvA8gvV1mSu1Ic3xMHmxA4CSA2w_g",
            # Macaroon that is malformed and has an invalid (non utf-8) identifier
            # The string is purposely cut to avoid triggering the github token
            # disclosure feature that this very function implements.
            "py"
            "pi-MDAwZWxvY2F0aW9uIAowMDM0aWRlbnRpZmllciBhmTAyMWY0YS0xYWQzLTQ3OGEtYjljZi1"
            "kMDU1NTkyMGYxYzcKMDAwZnNpZ25hdHVyZSAK",
        ],
    )
    def test_find_from_raw_not_found_or_invalid(self, macaroon_service, raw_macaroon):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.find_from_raw(raw_macaroon)

    def test_find_userid_no_macaroon(self, macaroon_service):
        assert macaroon_service.find_userid(None) is None

    def test_find_userid_invalid_macaroon(self, macaroon_service):
        raw_macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=str(uuid4()),
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        ).serialize()
        raw_macaroon = f"pypi-{raw_macaroon}"

        assert macaroon_service.find_userid(raw_macaroon) is None

    @pytest.mark.parametrize(
        "raw_macaroon",
        [
            "pypi-thiswillnotdeserialize",
            # Macaroon that is malformed and has an invalid (non utf-8) identifier
            # The string is purposely cut to avoid triggering the github token
            # disclosure feature that this very function implements.
            "py"
            "pi-MDAwZWxvY2F0aW9uIAowMDM0aWRlbnRpZmllciBhmTAyMWY0YS0xYWQzLTQ3OGEtYjljZi1"
            "kMDU1NTkyMGYxYzcKMDAwZnNpZ25hdHVyZSAK",
        ],
    )
    def test_find_userid_malformed_macaroon(self, macaroon_service, raw_macaroon):
        assert macaroon_service.find_userid(raw_macaroon) is None

    def test_find_userid_valid_macaroon_trailinglinebreak(self, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.ProjectName(normalized_names=["foo"])],
            user_id=user.id,
        )
        assert macaroon_service.find_userid(f"{raw_macaroon}\n") is None

    def test_find_userid_oidc_macaroon(self, macaroon_service):
        publisher = GitHubPublisherFactory.create()
        (
            raw_macaroon,
            _,
        ) = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id))],
            oidc_publisher_id=publisher.id,
        )
        assert macaroon_service.find_userid(raw_macaroon) is None

    def test_find_userid(self, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )
        user_id = macaroon_service.find_userid(raw_macaroon)

        assert user.id == user_id

    def test_verify_unprefixed_macaroon(self, macaroon_service, mocker):
        raw_macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=str(uuid4()),
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        ).serialize()

        with pytest.raises(
            services.InvalidMacaroonError, match="malformed or nonexistent macaroon"
        ):
            macaroon_service.verify(
                raw_macaroon,
                mocker.sentinel.request,
                mocker.sentinel.context,
                mocker.sentinel.permissions,
            )

    def test_verify_no_macaroon(self, macaroon_service, mocker):
        raw_macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=str(uuid4()),
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        ).serialize()
        raw_macaroon = f"pypi-{raw_macaroon}"

        with pytest.raises(
            services.InvalidMacaroonError, match="deleted or nonexistent macaroon"
        ):
            macaroon_service.verify(
                raw_macaroon,
                mocker.sentinel.request,
                mocker.sentinel.context,
                mocker.sentinel.permissions,
            )

    def test_verify_invalid_macaroon(
        self, mocker, db_request, user_service, macaroon_service
    ):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

        verify = mocker.patch.object(
            caveats, "verify", autospec=True, return_value=WarehouseDenied("foo")
        )

        request = db_request
        context = mocker.sentinel.context
        permissions = mocker.sentinel.permissions

        with pytest.raises(services.InvalidMacaroonError, match="foo"):
            macaroon_service.verify(raw_macaroon, request, context, permissions)
        verify.assert_called_once_with(
            mocker.ANY, mocker.ANY, request, context, permissions
        )

    def test_deserialize_raw_macaroon_when_none(self, mocker):
        _extract_func = mocker.patch.object(
            services, "_extract_raw_macaroon", autospec=True, return_value=None
        )

        with pytest.raises(
            services.InvalidMacaroonError, match="malformed or nonexistent macaroon"
        ):
            services.deserialize_raw_macaroon(None)

        _extract_func.assert_called_once_with(None)

    @pytest.mark.parametrize(
        "exception",
        [
            IndexError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            binascii.Error,
            struct.error,
            MacaroonDeserializationException,
            Exception,  # https://github.com/ecordell/pymacaroons/issues/50
        ],
    )
    def test_deserialize_raw_macaroon(self, mocker, exception):
        raw_macaroon = mocker.sentinel.raw_macaroon
        mocker.patch.object(
            services,
            "_extract_raw_macaroon",
            autospec=True,
            return_value=raw_macaroon,
        )
        mocker.patch.object(pymacaroons.Macaroon, "deserialize", side_effect=exception)

        with pytest.raises(services.InvalidMacaroonError):
            services.deserialize_raw_macaroon(raw_macaroon)

    def test_verify_malformed_macaroon(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify("pypi-thiswillnotdeserialize", None, None, None)

    def test_verify_valid_macaroon(self, mocker, db_request, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

        dm = macaroon_service.find_from_raw(raw_macaroon)
        # Add a database only caveat that has not been embedded into the macaroon
        dm.caveats = [*dm.caveats, caveats.Expiration(expires_at=5, not_before=2)]

        verify = mocker.patch.object(
            caveats, "verify", autospec=True, return_value=True
        )

        request = db_request
        context = mocker.sentinel.context
        permissions = mocker.sentinel.permissions

        assert macaroon_service.verify(raw_macaroon, request, context, permissions)
        verify.assert_called_once_with(
            mocker.ANY, dm.key, request, context, permissions
        )

        # Ensure that the macaroon that was verified is what was expected.
        vm = verify.call_args.args[0]
        assert vm.location == "fake location"
        assert vm.identifier == str(dm.id).encode("utf8")
        assert [c.to_dict() for c in vm.caveats] == [
            # The embedded RequestUser caveat
            {
                "cid": f'[3,"{user.id!s}"]',
                "cl": None,
                "vid": None,
            },
            # The database stored RequestUser caveat
            {
                "cid": f'[3,"{user.id!s}"]',
                "cl": None,
                "vid": None,
            },
            # The database stored Expiration caveat
            {"cid": "[0,5,2]", "cl": None, "vid": None},
        ]

    @pytest.fixture
    def user_macaroon(self, macaroon_service):
        """A user-scoped macaroon, as a (raw, database model) pair."""
        user = UserFactory.create()
        return macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

    def test_verify_records_unattenuated_macaroon(
        self, mocker, db_request, macaroon_service, user_macaroon
    ):
        raw_macaroon, _ = user_macaroon
        mocker.patch.object(caveats, "verify", autospec=True, return_value=True)

        macaroon_service.verify(
            raw_macaroon,
            db_request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        db_request.metrics.increment.assert_any_call(
            "warehouse.macaroon.verify.attenuated", tags=["attenuated:false"]
        )

    def test_verify_records_attenuated_macaroon(
        self, mocker, db_request, macaroon_service, user_macaroon
    ):
        raw_macaroon, _ = user_macaroon
        # Attenuate the macaroon the way an end user would, without telling us.
        m = services.deserialize_raw_macaroon(raw_macaroon)
        m.add_first_party_caveat(
            caveats.serialize(caveats.Expiration(expires_at=10, not_before=0))
        )
        mocker.patch.object(caveats, "verify", autospec=True, return_value=True)

        macaroon_service.verify(
            f"pypi-{m.serialize()}",
            db_request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        db_request.metrics.increment.assert_any_call(
            "warehouse.macaroon.verify.attenuated", tags=["attenuated:true"]
        )
        db_request.metrics.increment.assert_any_call(
            "warehouse.macaroon.verify.attenuation_kind", tags=["caveat:Expiration"]
        )

    def test_verify_records_macaroon_without_stored_caveats(
        self, mocker, db_request, macaroon_service, user_macaroon
    ):
        """Macaroons issued before we stored caveats have nothing to compare to."""
        raw_macaroon, dm = user_macaroon
        dm.caveats = []
        mocker.patch.object(caveats, "verify", autospec=True, return_value=True)

        macaroon_service.verify(
            raw_macaroon,
            db_request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        db_request.metrics.increment.assert_any_call(
            "warehouse.macaroon.verify.attenuated", tags=["attenuated:unknown"]
        )

    def test_verify_records_nothing_for_invalid_macaroon(
        self, mocker, db_request, macaroon_service, user_macaroon
    ):
        """Anyone can present a macaroon, so only verified ones are counted."""
        raw_macaroon, _ = user_macaroon
        mocker.patch.object(
            caveats, "verify", autospec=True, return_value=WarehouseDenied("foo")
        )

        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify(
                raw_macaroon,
                db_request,
                mocker.sentinel.context,
                mocker.sentinel.permission,
            )

        assert not [
            call
            for call in db_request.metrics.increment.call_args_list
            if call.args[0].startswith("warehouse.macaroon.verify.attenuat")
        ]

    def test_verify_signature_only(
        self,
        user_macaroon,
        macaroon_service,
    ):
        """
        We can verify a signature on a macaroon without contextually evaluating its
        caveats.
        """
        raw_macaroon, db_macaroon = user_macaroon

        assert macaroon_service.verify_signature_only(raw_macaroon) == db_macaroon

    def test_verify_signature_only_nonexistent(
        self,
        user_macaroon,
        macaroon_service,
    ):
        """
        Verifying only the signature on a macaroon fails if the macaroon doesn't
        exist in the DB.
        """

        raw_macaroon, db_macaroon = user_macaroon

        # Delete the macaroon so that lookup fails.
        macaroon_service.delete_macaroon(str(db_macaroon.id))

        with pytest.raises(services.InvalidMacaroonError, match="Macaroon not found"):
            macaroon_service.verify_signature_only(raw_macaroon)

    def test_verify_signature_only_invalid(
        self,
        user_macaroon,
        macaroon_service,
    ):
        """
        Verifying only the signature fails if the signature doesn't match.
        """

        raw_macaroon, db_macaroon = user_macaroon

        # Sanity check: the signature matches.
        assert macaroon_service.verify_signature_only(raw_macaroon) == db_macaroon

        # Replace the DB-side key so that the signature cannot possibly match.
        db_macaroon.key = b"banana"

        with pytest.raises(services.InvalidMacaroonError, match="Invalid signature"):
            macaroon_service.verify_signature_only(raw_macaroon)

    def test_verify_signature_only_invalid_identifier(self, macaroon_service):
        macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=b"\xff",
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        )

        with pytest.raises(
            services.InvalidMacaroonError, match="malformed macaroon identifier"
        ):
            macaroon_service.verify_signature_only(f"pypi-{macaroon.serialize()}")

    def test_delete_macaroon(self, user_service, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )
        macaroon_id = str(macaroon.id)

        macaroon_service.delete_macaroon(macaroon_id)

        assert macaroon_service.find_macaroon(macaroon_id) is None

    def test_delete_macaroon_no_macaroon(self, macaroon_service):
        assert macaroon_service.delete_macaroon("no such macaroon") is None

    def test_get_macaroon_by_description_no_macaroon(self, macaroon_service):
        user = UserFactory.create()
        assert (
            macaroon_service.get_macaroon_by_description(user.id, "no such description")
            is None
        )

    def test_get_macaroon_by_description(self, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [
                caveats.ProjectName(normalized_names=["foo", "bar"]),
                caveats.Expiration(expires_at=10, not_before=5),
            ],
            user_id=user.id,
        )

        dm = macaroon_service.find_macaroon(str(macaroon.id))

        assert (
            macaroon_service.get_macaroon_by_description(user.id, macaroon.description)
            == dm
        )

    def test_errors_with_wrong_caveats(self, macaroon_service):
        user = UserFactory.create()

        with pytest.raises(
            TypeError, match="scopes must be a list of Caveat instances"
        ):
            macaroon_service.create_macaroon(
                "fake location",
                "fake description",
                [{"version": 1, "permissions": "user"}],
                user_id=user.id,
            )


def _token(
    packets: list[tuple[int, bytes | None]],
    keep: int | None = None,
    extra: bytes = b"",
) -> str:
    """
    Build a `pypi-` token from raw v2 packets, however malformed, appending
    `extra` bytes verbatim and optionally keeping only the first `keep`
    characters of its base64 body.
    """
    serializer = BinarySerializer()
    data = bytearray([pymacaroons.MACAROON_V2])
    for field_type, payload in packets:
        serializer._append_packet(data, field_type, payload)
    data.extend(extra)

    body = base64.urlsafe_b64encode(bytes(data)).decode().rstrip("=")
    return "pypi-" + (body if keep is None else body[:keep])


_HEADER = [
    (BinarySerializer._LOCATION, b"pypi.org"),
    (BinarySerializer._IDENTIFIER, b"02ede3fe-dc00-45b9-9a13-9f16ad1c454d"),
    (BinarySerializer._EOS, None),
]


class TestDeserializePartialMacaroon:
    def test_truncated_mid_caveat(self):
        """A token cut off inside its first caveat, as a leak report would carry."""
        token = _token(
            [
                *_HEADER,
                (BinarySerializer._IDENTIFIER, b'[3,"%s"]' % (b"a" * 36)),
                (BinarySerializer._EOS, None),
            ],
            keep=75,
        )

        partial = services.deserialize_partial_macaroon(token)

        assert partial == services.PartialMacaroon(
            location="pypi.org",
            identifier="02ede3fe-dc00-45b9-9a13-9f16ad1c454d",
            identifier_complete=True,
            caveats=['[3," (truncated, 42 bytes declared)'],
            signature=None,
        )

    @pytest.mark.parametrize(
        ("suffix", "where"),
        [("\n", "a trailing newline"), (" ", "a trailing space"), ("\r\n", "a CRLF")],
    )
    def test_whitespace_around_the_token(self, suffix, where):
        """A pasted token brings whitespace with it, which is not data."""
        token = _token(
            [
                *_HEADER,
                (BinarySerializer._IDENTIFIER, b'[3,"%s"]' % (b"a" * 36)),
                (BinarySerializer._EOS, None),
            ],
            keep=75,
        )

        assert services.deserialize_partial_macaroon(
            token + suffix
        ) == services.deserialize_partial_macaroon(token)

    def test_truncated_mid_identifier(self):
        """A half-read identifier is no use for a lookup."""
        partial = services.deserialize_partial_macaroon(_token(_HEADER, keep=24))

        assert partial == services.PartialMacaroon(
            location="pypi.org",
            identifier="02ede (truncated, 36 bytes declared)",
            identifier_complete=False,
        )

    def test_truncated_before_any_payload(self):
        """A packet header with no payload after it still names a length."""
        partial = services.deserialize_partial_macaroon(_token(_HEADER, keep=4))

        assert partial == services.PartialMacaroon(
            location="(truncated, 8 bytes declared)"
        )

    def test_truncated_mid_packet_header(self):
        """A cut inside a packet's own varints ends the read."""
        token = _token([(BinarySerializer._LOCATION, b"pypi.org")], keep=3)

        assert services.deserialize_partial_macaroon(token) is None

    def test_long_caveat_uses_multibyte_length(self):
        """A payload over 127 bytes declares its length in two varint bytes."""
        token = _token(
            [
                *_HEADER,
                (BinarySerializer._IDENTIFIER, b'[1,["%s"]]' % (b"a" * 200)),
                (BinarySerializer._EOS, None),
            ],
            keep=80,
        )

        partial = services.deserialize_partial_macaroon(token)

        assert partial.caveats == ['[1,["aa (truncated, 208 bytes declared)']

    def test_malformed_header_still_yields_caveats_and_signature(self):
        """A whole macaroon that will not deserialize still gives up its fields."""
        token = _token(
            [
                (BinarySerializer._LOCATION, b"pypi.org"),
                (BinarySerializer._EOS, None),  # no identifier: invalid header
                (BinarySerializer._IDENTIFIER, b"\xff\xfe"),
                (BinarySerializer._EOS, None),
                (BinarySerializer._EOS, None),
                (BinarySerializer._SIGNATURE, bytes(range(4))),
            ]
        )

        with pytest.raises(services.InvalidMacaroonError):
            services.deserialize_raw_macaroon(token)

        assert services.deserialize_partial_macaroon(token) == services.PartialMacaroon(
            location="pypi.org",
            identifier=None,
            caveats=["fffe"],  # not valid UTF-8, so shown as hex
            signature="00010203",
        )

    def test_third_party_caveat_fields_are_ignored(self):
        """A third party caveat's location and key id have nothing to show."""
        token = _token(
            [
                *_HEADER,
                (BinarySerializer._LOCATION, b"elsewhere.example"),
                (BinarySerializer._IDENTIFIER, b"who knows"),
                (BinarySerializer._VID, b"key id"),
                (BinarySerializer._EOS, None),
            ]
        )

        partial = services.deserialize_partial_macaroon(token)

        assert partial.location == "pypi.org"
        assert partial.caveats == ["who knows"]

    def test_absurd_length_varint_stops_the_read(self):
        """A length varint longer than any real one ends the read."""
        token = _token(
            _HEADER,
            # A caveat identifier whose length runs to a fourth varint byte.
            extra=bytes([BinarySerializer._IDENTIFIER, 0x80, 0x80, 0x80, 0x01]),
        )

        partial = services.deserialize_partial_macaroon(token)

        assert partial.identifier == "02ede3fe-dc00-45b9-9a13-9f16ad1c454d"
        assert partial.caveats == []

    def test_oversized_token_is_not_walked(self):
        """A paste past a few kilobytes is refused."""
        token = _token(_HEADER, extra=bytes(services._MAX_TOKEN_BYTES))

        assert services.deserialize_partial_macaroon(token) is None

    @pytest.mark.parametrize(
        ("token", "reason"),
        [
            ("invalid", "no pypi- prefix"),
            ("pypi-A!!!", "body is not decodable base64"),
            ("pypi-AQEIcHlwaS5vcmc", "version 1, which we never issue"),
            ("pypi-Ag", "nothing after the version byte"),
            ("pypi-AgEIcHl\u2026", "a non-ASCII character, as when a UI elides"),
        ],
    )
    def test_nothing_readable(self, token, reason):
        assert services.deserialize_partial_macaroon(token) is None
