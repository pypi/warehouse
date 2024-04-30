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


import pretend
import pytest

from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    PendingActiveStatePublisherFactory,
)
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import _core
from warehouse.oidc.models.activestate import (
    ActiveStatePublisher,
    PendingActiveStatePublisher,
)

ORG_URL_NAME = "fakeorg"
PROJECT_NAME = "fakeproject"
ACTOR_ID = "00000000-0000-1000-8000-000000000002"
ACTOR = "fakeuser"
INGREDIENT = "fakeingredientname"
# This follows the format of the subject that ActiveState sends us.  We don't
# validate the format when verifying the JWT. That should happen when the
# Publisher is configured.  We just need to make sure that the subject matches
SUBJECT = f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}"


def test_lookup_strategies():
    assert (
        len(ActiveStatePublisher.__lookup_strategies__)
        == len(PendingActiveStatePublisher.__lookup_strategies__)
        == 1
    )


def new_signed_claims(
    sub: str = SUBJECT,
    actor: str = ACTOR,
    actor_id: str = ACTOR_ID,
    ingredient: str = INGREDIENT,
    organization: str = ORG_URL_NAME,
    org_id: str = "fakeorgid",
    project: str = PROJECT_NAME,
    project_id: str = "fakeprojectid",
    project_path: str = "fakeorg/fakeproject",
    project_visibility: str = "public",
    branch_id: str | None = None,
) -> SignedClaims:
    claims = SignedClaims(
        {
            "sub": sub,
            "actor": actor,
            "actor_id": actor_id,
            "ingredient": ingredient,
            "organization_id": org_id,
            "organization": organization,
            "project_visibility": project_visibility,
            "project_id": project_id,
            "project_path": project_path,
            "project": project,
            "builder": "pypi-publisher",
        }
    )
    if branch_id:
        claims["branch_id"] = branch_id
    return claims


class TestActiveStatePublisher:
    def test_publisher_name(self):
        publisher = ActiveStatePublisher()

        assert publisher.publisher_name == "ActiveState"

    def test_publisher_base_url(self):
        org_name = "fakeorg"
        project_name = "fakeproject"
        publisher = ActiveStatePublisher(
            organization=org_name, activestate_project_name=project_name
        )

        assert (
            publisher.publisher_base_url
            == f"https://platform.activestate.com/{org_name}/{project_name}"
        )

    def test_publisher_url(self):
        org_name = "fakeorg"
        project_name = "fakeproject"
        publisher = ActiveStatePublisher(
            organization=org_name, activestate_project_name=project_name
        )

        assert (
            publisher.publisher_url()
            == f"https://platform.activestate.com/{org_name}/{project_name}"
        )

    def test_stored_claims(self):
        publisher = ActiveStatePublisher(
            organization="fake", activestate_project_name="fake"
        )

        assert publisher.stored_claims() == {}

    def test_stringifies_as_project_url(self):
        org_name = "fakeorg"
        project_name = "fakeproject"
        publisher = ActiveStatePublisher(
            organization=org_name, activestate_project_name=project_name
        )

        assert (
            str(publisher)
            == f"https://platform.activestate.com/{org_name}/{project_name}"
        )

    def test_activestate_publisher_all_known_claims(self):
        assert ActiveStatePublisher.all_known_claims() == {
            # verifiable claims
            "organization",
            "project",
            "actor_id",
            "actor",
            "builder",
            "sub",
            "artifact_id",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "project_visibility",
            "project_path",
            "ingredient",
            "organization_id",
            "project_id",
        }

    def test_activestate_publisher_unaccounted_claims(self, monkeypatch):
        publisher = ActiveStatePublisher(
            organization=ORG_URL_NAME,
            activestate_project_name=PROJECT_NAME,
            actor_id=ACTOR_ID,
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = new_signed_claims()
        signed_claims["fake-claim"] = "fake"
        signed_claims["another-fake-claim"] = "also-fake"

        assert publisher.verify_claims(signed_claims=signed_claims)

        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for ActiveStatePublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    @pytest.mark.parametrize(
        ("claim_to_drop", "valid", "error_msg"),
        [
            ("organization", False, "Missing claim 'organization'"),
            ("project", False, "Missing claim 'project'"),
            ("actor_id", False, "Missing claim 'actor_id'"),
            ("actor", True, None),
            ("builder", False, "Missing claim 'builder'"),
            ("organization_id", True, None),
            ("project_id", True, None),
            ("project_visibility", True, None),
            ("project_path", True, None),
        ],
    )
    def test_activestate_publisher_missing_claims(
        self, monkeypatch, claim_to_drop: str, valid: bool, error_msg: str | None
    ):
        publisher = ActiveStatePublisher(
            organization=ORG_URL_NAME,
            activestate_project_name=PROJECT_NAME,
            actor_id=ACTOR_ID,
            actor=ACTOR,
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = new_signed_claims()
        signed_claims.pop(claim_to_drop)

        assert claim_to_drop not in signed_claims
        if valid:
            assert publisher.verify_claims(signed_claims=signed_claims) is valid
        else:
            with pytest.raises(InvalidPublisherError) as e:
                assert publisher.verify_claims(signed_claims=signed_claims)
            assert str(e.value) == error_msg
            assert sentry_sdk.capture_message.calls == [
                pretend.call(
                    "JWT for ActiveStatePublisher is missing claim: " + claim_to_drop
                )
            ]
            assert scope.fingerprint == [claim_to_drop]

    @pytest.mark.parametrize(
        ("expect", "actual", "valid"),
        [
            (ORG_URL_NAME, ORG_URL_NAME, True),
            (ORG_URL_NAME, PROJECT_NAME, False),
        ],
    )
    def test_activestate_publisher_org_id_verified(
        self, expect: str, actual: str, valid: bool
    ):
        publisher = ActiveStatePublisher(
            organization=actual,
            activestate_project_name=PROJECT_NAME,
            actor_id=ACTOR_ID,
            actor=ACTOR,
        )

        signed_claims = new_signed_claims(organization=expect)
        check = publisher.__required_verifiable_claims__["organization"]
        assert check(actual, expect, signed_claims) is valid

    @pytest.mark.parametrize(
        ("expect", "actual", "valid"),
        [
            (PROJECT_NAME, PROJECT_NAME, True),
            (PROJECT_NAME, ORG_URL_NAME, False),
        ],
    )
    def test_activestate_publisher_project_id_verified(
        self, expect: str, actual: str, valid: bool
    ):
        publisher = ActiveStatePublisher(
            organization=ORG_URL_NAME,
            activestate_project_name=actual,
            actor_id=ACTOR_ID,
            actor=ACTOR,
        )

        signed_claims = new_signed_claims(project=expect)
        check = publisher.__required_verifiable_claims__["project"]
        assert check(actual, expect, signed_claims) is valid

    @pytest.mark.parametrize(
        ("expect", "actual", "valid"),
        [
            (ACTOR_ID, ACTOR_ID, True),
            (ACTOR_ID, ORG_URL_NAME, False),
        ],
    )
    def test_activestate_publisher_user_id_verified(
        self, expect: str, actual: str, valid: bool
    ):
        publisher = ActiveStatePublisher(
            organization=ORG_URL_NAME,
            activestate_project_name=PROJECT_NAME,
            actor_id=actual,
            actor=ACTOR,
        )
        signed_claims = new_signed_claims(actor_id=expect)
        check = publisher.__required_verifiable_claims__["actor_id"]
        assert check(actual, expect, signed_claims) is valid

    @pytest.mark.parametrize(
        ("expected", "actual", "valid", "error_msg"),
        [
            # Both present: must match.
            (
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                True,
                None,
            ),
            # Both present: must match.
            (
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                "",
                False,
                "Missing 'subject' claim",
            ),
            # Wrong value, project, must fail.
            (
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                f"org:{ORG_URL_NAME}:project:{ORG_URL_NAME}",
                False,
                "Invalid 'subject' claim",
            ),
            # Wrong value, org_id, must fail.
            (
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                f"org:{PROJECT_NAME}:project:{PROJECT_NAME}",
                False,
                "Invalid 'subject' claim",
            ),
            # Just nonsenes, must fail.
            (
                f"org:{ORG_URL_NAME}:project:{PROJECT_NAME}",
                "Nonsense",
                False,
                "Invalid 'subject' claim. Wrong format",
            ),
        ],
    )
    def test_activestate_publisher_sub(
        self, expected: str, actual: str, valid: bool, error_msg: str | None
    ):
        check = ActiveStatePublisher.__required_verifiable_claims__["sub"]
        signed_claims = new_signed_claims(sub=actual)
        if valid:
            assert check(expected, actual, signed_claims) is True
        else:
            with pytest.raises(InvalidPublisherError) as e:
                check(expected, actual, signed_claims)
            assert str(e.value) == error_msg


class TestPendingActiveStatePublisher:
    def test_reify_does_not_exist_yet(self, db_request):
        pending_publisher: PendingActiveStatePublisher = (
            PendingActiveStatePublisherFactory.create()
        )
        assert (
            db_request.db.query(ActiveStatePublisher)
            .filter_by(
                organization=pending_publisher.organization,
                activestate_project_name=pending_publisher.activestate_project_name,
                actor_id=pending_publisher.actor_id,
                actor=pending_publisher.actor,
            )
            .one_or_none()
            is None
        )
        publisher = pending_publisher.reify(db_request.db)

        assert isinstance(publisher, ActiveStatePublisher)
        assert pending_publisher in db_request.db.deleted
        assert publisher.organization == pending_publisher.organization
        assert publisher.sub == pending_publisher.sub

    def test_reify_already_exists(self, db_request):
        existing_publisher: ActiveStatePublisher = ActiveStatePublisherFactory.create()
        pending_publisher = PendingActiveStatePublisherFactory.create(
            organization=existing_publisher.organization,
            activestate_project_name=existing_publisher.activestate_project_name,
            actor_id=existing_publisher.actor_id,
            actor=existing_publisher.actor,
        )
        publisher = pending_publisher.reify(db_request.db)

        assert existing_publisher == publisher
        assert pending_publisher in db_request.db.deleted
