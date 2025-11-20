# SPDX-License-Identifier: Apache-2.0

import uuid

import pretend
import pytest

from pyramid.authorization import Authenticated

from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
    SemaphorePublisherFactory,
)
from tests.common.db.organizations import OrganizationOIDCIssuerFactory
from warehouse.oidc import errors, utils
from warehouse.oidc.models import (
    SEMAPHORE_OIDC_ISSUER_URL_SUFFIX,
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    SemaphorePublisher,
)
from warehouse.oidc.utils import OIDC_PUBLISHER_CLASSES
from warehouse.organizations.models import OIDCIssuerType
from warehouse.utils.security_policy import principals_for


def test_find_publisher_by_issuer_bad_issuer_url():
    session = pretend.stub(scalar=lambda *stmt: None)

    with pytest.raises(errors.InvalidPublisherError):
        utils.find_publisher_by_issuer(
            session, "https://fake-issuer.url", pretend.stub()
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
            "iss": utils.GITLAB_OIDC_ISSUER_URL,
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


def test_find_publisher_by_issuer_semaphore(db_request):
    SemaphorePublisherFactory(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        organization="example-org",
        organization_id="org-id-1234",
        project="example-project",
        project_id="proj-id-5678",
        repo_slug="owner/repo",
    )

    signed_claims = {
        claim_name: "fake" for claim_name in SemaphorePublisher.all_known_claims()
    }
    signed_claims.update(
        {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj": "example-project",
            "prj_id": "proj-id-5678",
            "repo_slug": "owner/repo",
        }
    )

    assert utils.find_publisher_by_issuer(
        db_request.db,
        f"https://example-org{SEMAPHORE_OIDC_ISSUER_URL_SUFFIX}",
        signed_claims,
    ).id == uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_oidc_context_principals():
    assert principals_for(
        utils.PublisherTokenContext(publisher=pretend.stub(id=17), claims=None)
    ) == [
        Authenticated,
        "oidc:17",
    ]


def test_oidc_maps_consistent():
    for class_map in utils.OIDC_PUBLISHER_CLASSES.values():
        # The class mapping for pending and non-pending publisher models
        # should be distinct.
        assert class_map[True] != class_map[False]


def test_find_publisher_by_issuer_with_custom_issuer(db_request):
    """
    A custom OIDC issuer URL is properly resolved to a concrete publisher.
    """
    # Create organization and register a custom GitLab issuer URL
    custom_issuer_url = "https://gitlab.custom-company.com"
    OrganizationOIDCIssuerFactory.create(
        issuer_type=OIDCIssuerType.GitLab,
        issuer_url=custom_issuer_url,
    )

    # Create a GitLab publisher that would match the claims
    publisher = GitLabPublisherFactory(
        namespace="foo",
        project="bar",
        workflow_filepath="workflows/ci.yml",
        environment="",
        issuer_url=custom_issuer_url,
    )

    # Create signed claims that would come from the custom GitLab instance
    signed_claims = {
        claim_name: "fake" for claim_name in GitLabPublisher.all_known_claims()
    }
    signed_claims.update(
        {
            "iss": custom_issuer_url,
            "project_path": "foo/bar",
            "ci_config_ref_uri": "gitlab.custom-company.com/foo/bar//workflows/ci.yml@refs/heads/main",  # noqa: E501
        }
    )

    # This should successfully resolve the custom issuer URL to the GitLab publisher
    result = utils.find_publisher_by_issuer(
        db_request.db,
        utils.GITLAB_OIDC_ISSUER_URL,
        signed_claims,
    )

    assert result.id == publisher.id
