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

import uuid

import pretend
import pytest

from pyramid.authorization import Authenticated

from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
)
from warehouse.oidc import errors, utils
from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
)
from warehouse.oidc.utils import OIDC_PUBLISHER_CLASSES
from warehouse.utils.security_policy import principals_for


def test_find_publisher_by_issuer_bad_issuer_url():
    with pytest.raises(errors.InvalidPublisherError):
        utils.find_publisher_by_issuer(
            pretend.stub(), "https://fake-issuer.url", pretend.stub()
        )


@pytest.mark.parametrize(
    ("issuer_url", "publisher_cls_dict"), OIDC_PUBLISHER_CLASSES.items()
)
def test_find_publisher_by_issuer_checks_claims_existence(
    monkeypatch, issuer_url, publisher_cls_dict
):
    publisher_cls = pretend.stub(
        check_claims_existence=pretend.call_recorder(lambda x: None),
        lookup_by_claims=pretend.call_recorder(lambda x, y: None),
    )
    monkeypatch.setattr(
        utils,
        "OIDC_PUBLISHER_CLASSES",
        {issuer_url: {False: publisher_cls, True: publisher_cls}},
    )

    signed_claims = {
        claim_name: "fake"
        for claim_name in publisher_cls_dict[False].all_known_claims()
    }
    session = pretend.stub()
    utils.find_publisher_by_issuer(session, issuer_url, signed_claims)

    assert publisher_cls.check_claims_existence.calls == [pretend.call(signed_claims)]
    assert publisher_cls.lookup_by_claims.calls == [
        pretend.call(session, signed_claims)
    ]


@pytest.mark.parametrize(
    ("environment", "expected_id"),
    [
        (None, uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some_other_environment", uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some_environment", uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        ("sOmE_eNvIrOnMeNt", uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
    ],
)
def test_find_publisher_by_issuer_github(db_request, environment, expected_id):
    GitHubPublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        repository_owner="foo",
        repository_name="bar",
        repository_owner_id="1234",
        workflow_filename="ci.yml",
        environment="",  # No environment
    )
    GitHubPublisherFactory(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        repository_owner="foo",
        repository_name="bar",
        repository_owner_id="1234",
        workflow_filename="ci.yml",
        environment="some_environment",  # Environment set
    )

    signed_claims = {
        claim_name: "fake" for claim_name in GitHubPublisher.all_known_claims()
    }
    signed_claims.update(
        {
            "repository": "foo/bar",
            "job_workflow_ref": "foo/bar/.github/workflows/ci.yml@refs/heads/main",
            "repository_owner_id": "1234",
        }
    )
    if environment:
        signed_claims["environment"] = environment

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            utils.GITHUB_OIDC_ISSUER_URL,
            signed_claims,
        ).id
        == expected_id
    )


@pytest.mark.parametrize(
    ("environment", "expected_id"),
    [
        (None, uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some_other_environment", uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some_environment", uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
    ],
)
def test_find_publisher_by_issuer_gitlab(db_request, environment, expected_id):
    GitLabPublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        namespace="foo",
        project="bar",
        workflow_filepath="workflows/ci.yml",
        environment="",  # No environment
    )
    GitLabPublisherFactory(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        namespace="foo",
        project="bar",
        workflow_filepath="workflows/ci.yml",
        environment="some_environment",  # Environment set
    )

    signed_claims = {
        claim_name: "fake" for claim_name in GitLabPublisher.all_known_claims()
    }

    signed_claims.update(
        {
            "project_path": "foo/bar",
            "ci_config_ref_uri": "gitlab.com/foo/bar//workflows/ci.yml@refs/heads/main",
        }
    )
    if environment:
        signed_claims["environment"] = environment

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            utils.GITLAB_OIDC_ISSUER_URL,
            signed_claims,
        ).id
        == expected_id
    )


@pytest.mark.parametrize(
    ("sub", "expected_id"),
    [
        ("some-other-subject", uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some-subject", uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
    ],
)
def test_find_publisher_by_issuer_google(db_request, sub, expected_id):
    GooglePublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="fake@example.com",
        sub="",  # No subject
    )
    GooglePublisherFactory(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        email="fake@example.com",
        sub="some-subject",  # Subject set
    )

    signed_claims = {
        claim_name: "fake" for claim_name in GooglePublisher.all_known_claims()
    }

    signed_claims.update(
        {
            "email": "fake@example.com",
            "sub": sub,
        }
    )

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            utils.GOOGLE_OIDC_ISSUER_URL,
            signed_claims,
        ).id
        == expected_id
    )


@pytest.mark.parametrize(
    (
        "expected_id",
        "sub",
        "organization",
        "project",
        "actor_id",
        "actor",
        "ingredient_name",
    ),
    [
        (
            uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "org:fakeorg1:project:fakeproject1",
            "fakeorg1",
            "fakeproject1",
            "00000000-1000-8000-0000-000000000003",
            "fakeuser1",
            "fakeingredient1",
        ),
        (
            uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "org:fakeorg2:project:fakeproject2",
            "fakeorg2",
            "fakeproject2",
            "00000000-1000-8000-0000-000000000006",
            "fakeuser2",
            "fakeingredient2",
        ),
        (
            uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            "org:fakeorg3:project:fakeproject3",
            "fakeorg3",
            "fakeproject3",
            "00000000-1000-8000-0000-000000000009",
            "fakeuser3",
            "fakeingredient3",
        ),
    ],
)
def test_find_publisher_by_issuer_activestate(
    db_request,
    sub: str,
    expected_id: str,
    organization: str,
    project: str,
    actor_id: str,
    actor: str,
    ingredient_name: str,
):
    ActiveStatePublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        organization="fakeorg1",
        activestate_project_name="fakeproject1",
        actor_id="00000000-1000-8000-0000-000000000003",
        actor="fakeuser1",
    )
    ActiveStatePublisherFactory(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        organization="fakeorg2",
        activestate_project_name="fakeproject2",
        actor_id="00000000-1000-8000-0000-000000000006",
        actor="fakeuser2",
    )
    ActiveStatePublisherFactory(
        id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        organization="fakeorg3",
        activestate_project_name="fakeproject3",
        actor_id="00000000-1000-8000-0000-000000000009",
        actor="fakeuser3",
    )

    signed_claims = {
        claim_name: "fake" for claim_name in ActiveStatePublisher.all_known_claims()
    }

    signed_claims.update(
        {
            "sub": sub,
            "organization": organization,
            "project": project,
            "actor_id": actor_id,
            "actor": actor,
        }
    )

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            utils.ACTIVESTATE_OIDC_ISSUER_URL,
            signed_claims,
        ).id
        == expected_id
    )


def test_oidc_context_principals():
    assert principals_for(
        utils.PublisherTokenContext(publisher=pretend.stub(id=17), claims=None)
    ) == [
        Authenticated,
        "oidc:17",
    ]


def test_oidc_maps_consistent():
    # Our various mappings should have equivalent cardinalities.
    assert len(utils.OIDC_ISSUER_URLS) == len(utils.OIDC_ISSUER_SERVICE_NAMES)
    assert len(utils.OIDC_ISSUER_URLS) == len(utils.OIDC_ISSUER_ADMIN_FLAGS)
    assert len(utils.OIDC_ISSUER_URLS) == len(utils.OIDC_PUBLISHER_CLASSES)

    for iss in utils.OIDC_ISSUER_URLS:
        # Each issuer should be present in each mapping.
        assert iss in utils.OIDC_ISSUER_SERVICE_NAMES
        assert iss in utils.OIDC_ISSUER_ADMIN_FLAGS
        assert iss in utils.OIDC_PUBLISHER_CLASSES

    for class_map in utils.OIDC_PUBLISHER_CLASSES.values():
        # The class mapping for pending and non-pending publisher models
        # should be distinct.
        assert class_map[True] != class_map[False]
