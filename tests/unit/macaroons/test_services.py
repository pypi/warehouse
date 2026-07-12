# SPDX-License-Identifier: Apache-2.0

import binascii
import struct

from uuid import uuid4

import pymacaroons
import pytest

from pymacaroons.exceptions import MacaroonDeserializationException

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

    def test_verify_invalid_macaroon(self, mocker, user_service, macaroon_service):
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

        request = mocker.sentinel.request
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

    def test_verify_valid_macaroon(self, mocker, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )

        verify = mocker.patch.object(
            caveats, "verify", autospec=True, return_value=True
        )

        request = mocker.sentinel.request
        context = mocker.sentinel.context
        permissions = mocker.sentinel.permissions

        assert macaroon_service.verify(raw_macaroon, request, context, permissions)
        verify.assert_called_once_with(
            mocker.ANY, mocker.ANY, request, context, permissions
        )

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
