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

import binascii

from unittest import mock
from uuid import uuid4

import pretend
import pymacaroons
import pytest

from pymacaroons.exceptions import MacaroonDeserializationException

from warehouse.macaroons import services
from warehouse.macaroons.models import Macaroon

from ...common.db.accounts import UserFactory


def test_database_macaroon_factory():
    db = pretend.stub()
    request = pretend.stub(db=db)

    service = services.database_macaroon_factory(pretend.stub(), request)
    assert service.db is db


class TestDatabaseMacaroonService:
    def test_creation(self):
        session = pretend.stub()
        service = services.DatabaseMacaroonService(session)

        assert service.db is session

    @pytest.mark.parametrize(
        ["raw_macaroon", "result"],
        [
            (None, None),
            ("noprefixhere", None),
            ("invalid:prefix", None),
            ("pypi-validprefix", "validprefix"),
        ],
    )
    def test_extract_raw_macaroon(self, macaroon_service, raw_macaroon, result):
        assert macaroon_service._extract_raw_macaroon(raw_macaroon) == result

    def test_find_macaroon_invalid_macaroon(self, macaroon_service):
        assert macaroon_service.find_macaroon(str(uuid4())) is None

    def test_find_macaroon(self, user_service, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        dm = macaroon_service.find_macaroon(str(macaroon.id))

        assert isinstance(dm, Macaroon)
        assert macaroon.id == dm.id

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

    def test_find_userid_malformed_macaroon(self, macaroon_service):
        assert macaroon_service.find_userid(f"pypi-thiswillnotdeserialize") is None

    def test_find_userid_valid_macaroon_trailinglinebreak(self, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )
        assert macaroon_service.find_userid(f"{raw_macaroon}\n") is None

    def test_find_userid(self, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )
        user_id = macaroon_service.find_userid(raw_macaroon)

        assert user.id == user_id

    def test_verify_unprefixed_macaroon(self, macaroon_service):
        raw_macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=str(uuid4()),
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        ).serialize()

        with pytest.raises(services.InvalidMacaroon):
            macaroon_service.verify(
                raw_macaroon, pretend.stub(), pretend.stub(), pretend.stub()
            )

    def test_verify_no_macaroon(self, macaroon_service):
        raw_macaroon = pymacaroons.Macaroon(
            location="fake location",
            identifier=str(uuid4()),
            key=b"fake key",
            version=pymacaroons.MACAROON_V2,
        ).serialize()
        raw_macaroon = f"pypi-{raw_macaroon}"

        with pytest.raises(services.InvalidMacaroon):
            macaroon_service.verify(
                raw_macaroon, pretend.stub(), pretend.stub(), pretend.stub()
            )

    def test_verify_invalid_macaroon(self, monkeypatch, user_service, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        verifier_obj = pretend.stub(verify=pretend.call_recorder(lambda k: False))
        verifier_cls = pretend.call_recorder(lambda *a: verifier_obj)
        monkeypatch.setattr(services, "Verifier", verifier_cls)

        context = pretend.stub()
        principals = pretend.stub()
        permissions = pretend.stub()

        with pytest.raises(services.InvalidMacaroon):
            macaroon_service.verify(raw_macaroon, context, principals, permissions)
        assert verifier_cls.calls == [
            pretend.call(mock.ANY, context, principals, permissions)
        ]

    def test_deserialize_raw_macaroon_when_none(self, macaroon_service):
        raw_macaroon = pretend.stub()
        macaroon_service._extract_raw_macaroon = pretend.call_recorder(lambda a: None)

        with pytest.raises(services.InvalidMacaroon):
            macaroon_service._deserialize_raw_macaroon(raw_macaroon)

        assert macaroon_service._extract_raw_macaroon.calls == [
            pretend.call(raw_macaroon),
        ]

    @pytest.mark.parametrize(
        "exception",
        [
            binascii.Error,
            MacaroonDeserializationException,
        ],
    )
    def test_deserialize_raw_macaroon(self, monkeypatch, macaroon_service, exception):
        raw_macaroon = pretend.stub()
        macaroon_service._extract_raw_macaroon = pretend.call_recorder(
            lambda a: raw_macaroon
        )
        monkeypatch.setattr(
            pymacaroons.Macaroon, "deserialize", pretend.raiser(exception)
        )

        with pytest.raises(services.InvalidMacaroon):
            macaroon_service._deserialize_raw_macaroon(raw_macaroon)

    def test_verify_malformed_macaroon(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroon):
            macaroon_service.verify(f"pypi-thiswillnotdeserialize", None, None, None)

    def test_verify_valid_macaroon(self, monkeypatch, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, _ = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        verifier_obj = pretend.stub(verify=pretend.call_recorder(lambda k: True))
        verifier_cls = pretend.call_recorder(lambda *a: verifier_obj)
        monkeypatch.setattr(services, "Verifier", verifier_cls)

        context = pretend.stub()
        principals = pretend.stub()
        permissions = pretend.stub()

        assert macaroon_service.verify(raw_macaroon, context, principals, permissions)
        assert verifier_cls.calls == [
            pretend.call(mock.ANY, context, principals, permissions)
        ]

    def test_delete_macaroon(self, user_service, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )
        macaroon_id = str(macaroon.id)

        macaroon_service.delete_macaroon(macaroon_id)

        assert macaroon_service.find_macaroon(macaroon_id) is None

    def test_get_macaroon_by_description_no_macaroon(self, macaroon_service):
        user = UserFactory.create()
        assert (
            macaroon_service.get_macaroon_by_description(user.id, "no such description")
            is None
        )

    def test_get_macaroon_by_description(self, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        dm = macaroon_service.find_macaroon(str(macaroon.id))

        assert (
            macaroon_service.get_macaroon_by_description(user.id, macaroon.description)
            == dm
        )
