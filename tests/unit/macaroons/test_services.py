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

from uuid import uuid4

import pretend
import pypitoken
import pytest

from warehouse.macaroons import services
from warehouse.macaroons.models import Macaroon

from ...common.db.accounts import UserFactory


def test_generate_key():
    key = services._generate_key()

    assert isinstance(key, bytes)
    assert len(key) == 32


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

    def test_find_from_raw(self, user_service, macaroon_service):
        user = UserFactory.create()
        serialized, macaroon = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        dm = macaroon_service.find_from_raw(serialized)

        assert isinstance(dm, Macaroon)
        assert macaroon.id == dm.id

    @pytest.mark.parametrize(
        "raw_macaroon",
        [
            "pypi-aaaa",  # Invalid macaroon
            pypitoken.Token.create(
                domain="example.com",
                identifier=str(uuid4()),
                key=b"fake key",
            ).dump(),
        ],
    )
    def test_find_from_raw_not_found_or_invalid(self, macaroon_service, raw_macaroon):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.find_from_raw(raw_macaroon)

    def test_find_userid_invalid_macaroon(self, macaroon_service):
        raw_macaroon = pypitoken.Token.create(
            domain="example.com",
            identifier=str(uuid4()),
            key=b"fake key",
        ).dump()

        assert macaroon_service.find_userid(raw_macaroon) is None

    def test_find_userid_malformed_macaroon(self, macaroon_service):
        assert macaroon_service.find_userid("pypi-thiswillnotdeserialize") is None

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

    def test_verify_bad_macaroon(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify(
                "foo", pretend.stub(), pretend.stub(), pretend.stub()
            )

    def test_verify_no_macaroon(self, macaroon_service):
        raw_macaroon = pypitoken.Token.create(
            domain="example.com",
            identifier=str(uuid4()),
            key=b"fake key",
        ).dump()

        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify(
                raw_macaroon, pretend.stub(), pretend.stub(), pretend.stub()
            )

    def test_verify_invalid_macaroon(self, monkeypatch, user_service, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, dm = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        token_obj = pretend.stub(
            check=pretend.call_recorder(pretend.raiser(pypitoken.ValidationError)),
            identifier=str(dm.id),
            prefix="pypi",
        )
        token_cls = pretend.stub(load=lambda *a: token_obj)

        monkeypatch.setattr(pypitoken, "Token", token_cls)

        context = pretend.stub(normalized_name="foo")
        principals = pretend.stub()
        permissions = pretend.stub()

        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify(raw_macaroon, context, principals, permissions)
        assert token_obj.check.calls == [pretend.call(key=dm.key, project="foo")]

    def test_deserialize_raw_macaroon(self, macaroon_service):
        token = pypitoken.Token.create(domain="pypi.org", identifier="b", key="c")
        serialized = token.dump()

        result = macaroon_service._deserialize_raw_macaroon(serialized)

        assert result.dump() == serialized

    def test_deserialize_raw_macaroon_wrong_prefix(self, macaroon_service):
        token = pypitoken.Token.create(
            domain="pypi.org", identifier="b", key="c", prefix="wrong"
        )
        serialized = token.dump()
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service._deserialize_raw_macaroon(serialized)

    def test_deserialize_raw_macaroon_wrong_format(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service._deserialize_raw_macaroon("foo")

    def test_deserialize_raw_macaroon_wrong_token(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service._deserialize_raw_macaroon("pypi-foo")

    def test_verify_malformed_macaroon(self, macaroon_service):
        with pytest.raises(services.InvalidMacaroonError):
            macaroon_service.verify("pypi-thiswillnotdeserialize", None, None, None)

    def test_verify_valid_macaroon(self, monkeypatch, macaroon_service):
        user = UserFactory.create()
        raw_macaroon, dm = macaroon_service.create_macaroon(
            "fake location", user.id, "fake description", {"fake": "caveats"}
        )

        token_obj = pretend.stub(
            check=pretend.call_recorder(lambda **a: None),
            identifier=str(dm.id),
            prefix="pypi",
        )
        token_cls = pretend.stub(load=pretend.call_recorder(lambda *a: token_obj))
        monkeypatch.setattr(pypitoken, "Token", token_cls)

        context = pretend.stub(normalized_name="foo")
        principals = pretend.stub()
        permissions = pretend.stub()

        assert macaroon_service.verify(raw_macaroon, context, principals, permissions)
        assert token_obj.check.calls == [pretend.call(key=dm.key, project="foo")]

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

    @pytest.mark.parametrize(
        "description",
        [
            {},
            {"projects": ["baz", "yay"]},
        ],
    )
    def test_describe_caveats(self, macaroon_service, description):
        token = pypitoken.Token.create(
            domain="example.com", identifier="foo", key="bar"
        )
        token.restrict(**description)
        caveat = token.restrictions[0].dump()
        assert macaroon_service.describe_caveats(caveat) == description
