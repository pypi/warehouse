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

from tests.common.db.oidc import GitHubPublisherFactory, GooglePublisherFactory
from warehouse.oidc import errors, utils
from warehouse.utils.security_policy import principals_for


def test_find_publisher_by_issuer_bad_issuer_url():
    with pytest.raises(errors.InvalidPublisherError):
        utils.find_publisher_by_issuer(
            pretend.stub(), "https://fake-issuer.url", pretend.stub()
        )


@pytest.mark.parametrize(
    "environment, expected_id",
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
        "repository": "foo/bar",
        "job_workflow_ref": "foo/bar/.github/workflows/ci.yml@refs/heads/main",
        "repository_owner_id": "1234",
    }
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
    "sub, expected_id",
    [
        ("some-other-subject", uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("some-subject", uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
    ],
)
def test_find_publisher_by_issuer_google(db_request, sub, expected_id):
    GooglePublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="fake@example.com",
        sub=None,  # No subject
    )
    GooglePublisherFactory(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        email="fake@example.com",
        sub="some-subject",  # Subject set
    )

    signed_claims = {
        "email": "fake@example.com",
        "sub": sub,
    }

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            utils.GOOGLE_OIDC_ISSUER_URL,
            signed_claims,
        ).id
        == expected_id
    )


def test_oidc_context_principals():
    assert principals_for(
        utils.OIDCContext(publisher=pretend.stub(id=17), claims=None)
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
