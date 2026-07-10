# SPDX-License-Identifier: Apache-2.0

import dataclasses
import time

import pytest

from pydantic.dataclasses import dataclass
from pymacaroons import Macaroon
from pyramid.testing import DummySecurityPolicy

from warehouse.accounts import _oidc_publisher
from warehouse.accounts.utils import UserContext
from warehouse.macaroons import caveats
from warehouse.macaroons.caveats import (
    Caveat,
    CaveatError,
    Expiration,
    Failure,
    OIDCPublisher,
    ProjectID,
    ProjectName,
    RequestUser,
    Success,
    deserialize,
    serialize,
    verify,
)
from warehouse.macaroons.caveats._core import _CaveatRegistry
from warehouse.oidc.utils import PublisherTokenContext

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import ProjectFactory


@dataclass(frozen=True)
class SampleCaveat(Caveat):
    first: int
    second: int = 2
    third: int = dataclasses.field(default_factory=lambda: 3)


def test_bools():
    assert bool(Success()) is True
    assert bool(Failure("anything")) is False


def test_caveat_verify_fails(mocker):
    caveat = Caveat()
    with pytest.raises(NotImplementedError):
        caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )


@pytest.mark.parametrize(
    ("caveat", "expected"),
    [
        (Expiration(expires_at=50, not_before=10), b"[0,50,10]"),
        (ProjectName(normalized_names=["foo", "bar"]), b'[1,["foo","bar"]]'),
        (
            ProjectID(project_ids=["123uuid", "456uuid"]),
            b'[2,["123uuid","456uuid"]]',
        ),
        (RequestUser(user_id="a uuid"), b'[3,"a uuid"]'),
    ],
)
def test_serialization(caveat, expected):
    assert serialize(caveat) == expected


@pytest.mark.parametrize(
    ("caveat", "expected"),
    [
        (Expiration(expires_at=50, not_before=10), [[0, 50, 10]]),
        (ProjectName(normalized_names=["foo", "bar"]), [[1, ["foo", "bar"]]]),
        (
            ProjectID(project_ids=["123uuid", "456uuid"]),
            [[2, ["123uuid", "456uuid"]]],
        ),
        (RequestUser(user_id="a uuid"), [[3, "a uuid"]]),
    ],
)
def test_serialization_onto_events(caveat, expected, db_request):
    user = UserFactory()
    user.record_event(
        tag="foobar", request=db_request, additional={"caveats": [caveat]}
    )
    assert user.events[0].additional["caveats"] == expected


class TestDeserialization:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            # Current Caveat Style
            (b"[0,50,10]", Expiration(expires_at=50, not_before=10)),
            (b'[1,["foo","bar"]]', ProjectName(normalized_names=["foo", "bar"])),
            (
                b'[2,["123uuid","456uuid"]]',
                ProjectID(project_ids=["123uuid", "456uuid"]),
            ),
            (b'[3,"a uuid"]', RequestUser(user_id="a uuid")),
            (
                b'[4,"somepublisher"]',
                OIDCPublisher(oidc_publisher_id="somepublisher"),
            ),
            # Legacy Caveat Style
            (b'{"exp": 50, "nbf": 10}', Expiration(expires_at=50, not_before=10)),
            (
                b'{"version": 1, "permissions": {"projects": ["foo", "bar"]}}',
                ProjectName(normalized_names=["foo", "bar"]),
            ),
            (
                b'{"project_ids": ["123uuid", "456uuid"]}',
                ProjectID(project_ids=["123uuid", "456uuid"]),
            ),
        ],
    )
    def test_valid_deserialization(self, data, expected):
        assert deserialize(data) == expected

    @pytest.mark.parametrize(
        "data",
        [
            b'{"version": 1}',
            b'{"version": 1, "permissions": "user"}',
            b'{"version": 1, "permissions": []}',
            b'{"version": 1, "permissions": {"otherkey": "foo"}}',
            b'{"exp": 1}',
            b'{"nbf": 1}',
            b'[0,"50",10]',
            b"[0,5]",
            b'"foo"',
            b"null",
            b"[]",
            b"[9999999]",
        ],
    )
    def test_invalid_deserialization(self, data):
        with pytest.raises(CaveatError):
            deserialize(data)

    def test_valid_test_valid_deserialization_request_user(
        self, pyramid_request, pyramid_config
    ):
        pyramid_request.user = UserFactory.build(id="a uuid")
        assert deserialize(b'{"version": 1, "permissions": "user"}') == RequestUser(
            user_id="a uuid"
        )

    def test_invalid_deserialization_request_user(
        self, pyramid_request, pyramid_config
    ):
        pyramid_request.user = None
        with pytest.raises(CaveatError):
            deserialize(b'{"version": 1, "permissions": "user"}')

    def test_deserialize_with_defaults(self):
        assert SampleCaveat.__deserialize__([1]) == SampleCaveat(
            first=1, second=2, third=3
        )
        assert SampleCaveat.__deserialize__([1, 5]) == SampleCaveat(
            first=1, second=5, third=3
        )
        assert SampleCaveat.__deserialize__([1, 5, 7]) == SampleCaveat(
            first=1, second=5, third=7
        )


class TestExpirationCaveat:
    def test_verify_not_before(self, mocker):
        not_before = int(time.time()) + 60
        expiry = not_before + 60

        caveat = Expiration(expires_at=expiry, not_before=not_before)
        result = caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Failure("token is expired")

    def test_verify_already_expired(self, mocker):
        not_before = int(time.time()) - 10
        expiry = not_before - 5

        caveat = Expiration(expires_at=expiry, not_before=not_before)
        result = caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Failure("token is expired")

    def test_verify_ok(self, mocker):
        not_before = int(time.time()) - 10
        expiry = int(time.time()) + 60

        caveat = Expiration(expires_at=expiry, not_before=not_before)
        result = caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Success()


class TestProjectNameCaveat:
    def test_verify_invalid_context(self, mocker):
        caveat = ProjectName(normalized_names=[])
        result = caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Failure(
            "project-scoped token used outside of a project context"
        )

    def test_verify_invalid_project_id(self, db_request, mocker):
        project = ProjectFactory.create(name="foobar")

        caveat = ProjectName(normalized_names=["not_foobar"])
        result = caveat.verify(db_request, project, mocker.sentinel.permission)

        assert result == Failure(
            f"project-scoped token is not valid for project: {project.name!r}"
        )

    def test_verify_ok(self, db_request, mocker):
        project = ProjectFactory.create(name="foobar")

        caveat = ProjectName(normalized_names=["foobar"])
        result = caveat.verify(db_request, project, mocker.sentinel.permission)

        assert result == Success()


class TestProjectIDsCaveat:
    def test_verify_invalid_context(self, mocker):
        caveat = ProjectID(project_ids=[])
        result = caveat.verify(
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Failure(
            "project-scoped token used outside of a project context"
        )

    def test_verify_invalid_project_id(self, db_request, mocker):
        project = ProjectFactory.create(name="foobar")

        caveat = ProjectID(project_ids=["not-foobars-uuid"])
        result = caveat.verify(db_request, project, mocker.sentinel.permission)

        assert result == Failure(
            f"project-scoped token is not valid for project: {project.name!r}"
        )

    def test_verify_ok(self, db_request, mocker):
        project = ProjectFactory.create(name="foobar")

        caveat = ProjectID(project_ids=[str(project.id)])
        result = caveat.verify(db_request, project, mocker.sentinel.permission)

        assert result == Success()


class TestRequestUserCaveat:
    def test_verify_no_identity(self, pyramid_request, mocker):
        # pyramid_request.identity defaults to None with no policy registered.
        caveat = RequestUser(user_id="invalid")
        result = caveat.verify(
            pyramid_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure("token with user restriction without a user")

    def test_verify_invalid_identity_no_user(
        self, pyramid_request, pyramid_config, mocker
    ):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=mocker.sentinel.identity)
        )

        caveat = RequestUser(user_id="invalid")
        result = caveat.verify(
            pyramid_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure("token with user restriction without a user")

    def test_verify_invalid_identity_no_macaroon(
        self, db_request, pyramid_config, mocker
    ):
        user = UserFactory.create()
        user_context = UserContext(user, None)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=user_context))

        caveat = RequestUser(user_id=str(user.id))
        result = caveat.verify(
            db_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure("token with user restriction without a macaroon")

    def test_verify_invalid_user_id(self, db_request, pyramid_config, mocker):
        user = UserFactory.create()
        user_context = UserContext(user, mocker.sentinel.macaroon)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=user_context))

        caveat = RequestUser(user_id="invalid")
        result = caveat.verify(
            db_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure(
            "current user does not match user restriction in token"
        )

    def test_verify_ok(self, db_request, pyramid_config, mocker):
        user = UserFactory.create()
        user_context = UserContext(user, mocker.sentinel.macaroon)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=user_context))

        caveat = RequestUser(user_id=str(user.id))
        result = caveat.verify(
            db_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Success()


class TestOIDCPublisherCaveat:
    def test_verify_no_identity(self, pyramid_request, mocker):
        # pyramid_request.oidc_publisher defaults to None.
        caveat = OIDCPublisher(oidc_publisher_id="invalid")
        result = caveat.verify(
            pyramid_request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )

        assert result == Failure(
            "OIDC scoped token used outside of an OIDC identified request"
        )

    def test_verify_invalid_publisher_id(self, db_request, pyramid_config, mocker):
        identity = PublisherTokenContext(GitHubPublisherFactory.create(), None)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=identity))
        db_request.oidc_publisher = _oidc_publisher(db_request)

        caveat = OIDCPublisher(oidc_publisher_id="invalid")
        result = caveat.verify(
            db_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure(
            "current OIDC publisher does not match publisher restriction in token"
        )

    def test_verify_invalid_context(self, db_request, pyramid_config, mocker):
        identity = PublisherTokenContext(GitHubPublisherFactory.create(), None)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=identity))
        db_request.oidc_publisher = _oidc_publisher(db_request)

        caveat = OIDCPublisher(oidc_publisher_id=str(db_request.oidc_publisher.id))
        result = caveat.verify(
            db_request, mocker.sentinel.context, mocker.sentinel.permission
        )

        assert result == Failure("OIDC scoped token used outside of a project context")

    def test_verify_invalid_project(self, db_request, pyramid_config, mocker):
        foobar = ProjectFactory.create(name="foobar")
        foobaz = ProjectFactory.create(name="foobaz")

        # This OIDC publisher is only registered to "foobar", so it should
        # not verify a caveat presented for "foobaz".
        identity = PublisherTokenContext(
            GitHubPublisherFactory.create(projects=[foobar]), None
        )
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=identity))
        db_request.oidc_publisher = _oidc_publisher(db_request)
        caveat = OIDCPublisher(oidc_publisher_id=str(db_request.oidc_publisher.id))

        result = caveat.verify(db_request, foobaz, mocker.sentinel.permission)

        assert result == Failure("OIDC scoped token is not valid for project 'foobaz'")

    def test_verify_ok(self, db_request, pyramid_config, mocker):
        foobar = ProjectFactory.create(name="foobar")

        # This OIDC publisher is only registered to "foobar", so it should
        # not verify a caveat presented for "foobaz".
        identity = PublisherTokenContext(
            GitHubPublisherFactory.create(projects=[foobar]), None
        )
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=identity))
        db_request.oidc_publisher = _oidc_publisher(db_request)
        caveat = OIDCPublisher(oidc_publisher_id=str(db_request.oidc_publisher.id))

        result = caveat.verify(db_request, foobar, mocker.sentinel.permission)

        assert result == Success()


class TestCaveatRegistry:
    def test_cannot_reuse_tag(self):
        registry = _CaveatRegistry()
        registry.add(0, Expiration)
        with pytest.raises(TypeError):
            registry.add(0, ProjectName)


class TestVerification:
    def test_verify_invalid_signature(self, mocker):
        m = Macaroon(location="somewhere", identifier="something", key=b"a secure key")
        status = verify(
            m,
            b"a different key",
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )
        assert not status
        assert status.msg == "signatures do not match"

    def test_caveat_returns_false(self, mocker):
        m = Macaroon(location="somewhere", identifier="something", key=b"a secure key")
        m.add_first_party_caveat(serialize(Expiration(expires_at=10, not_before=0)))
        status = verify(
            m,
            b"a secure key",
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )
        assert not status
        assert status.msg == "token is expired"

    def test_caveat_errors_on_deserialize(self, mocker):
        m = Macaroon(location="somewhere", identifier="something", key=b"a secure key")
        m.add_first_party_caveat(b"[]")
        status = verify(
            m,
            b"a secure key",
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )
        assert not status
        assert status.msg == "caveat array cannot be empty"

    def test_valid_caveat(self, mocker):
        now = int(time.time())
        m = Macaroon(location="somewhere", identifier="something", key=b"a secure key")
        m.add_first_party_caveat(
            serialize(Expiration(expires_at=now + 1000, not_before=now - 1000))
        )
        status = verify(
            m,
            b"a secure key",
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )
        assert status
        assert status.msg == "signature and caveats OK"

    def test_generic_exception(self, mocker):
        mocker.patch.object(
            caveats,
            "deserialize",
            autospec=True,
            side_effect=Exception("my generic exception"),
        )

        m = Macaroon(location="somewhere", identifier="something", key=b"a secure key")
        m.add_first_party_caveat(serialize(Expiration(expires_at=1, not_before=1)))
        status = verify(
            m,
            b"a secure key",
            mocker.sentinel.request,
            mocker.sentinel.context,
            mocker.sentinel.permission,
        )
        assert not status
        assert status.msg == "unknown error"
