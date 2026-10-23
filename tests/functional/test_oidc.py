# SPDX-License-Identifier: Apache-2.0

import json
import time

from http import HTTPStatus

import jwt
import pytest
import responses

from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms
from pyramid_services import IServiceRegistry, ProxyFactory

from tests.common.db.oidc import (
    BuildkitePublisherFactory,
    PendingBuildkitePublisherFactory,
)
from tests.common.db.packaging import ProjectFactory
from warehouse.oidc import interfaces as oidc_interfaces, services as oidc_services
from warehouse.oidc.models import BUILDKITE_OIDC_ISSUER_URL, PendingBuildkitePublisher
from warehouse.packaging.models import Project


class _InMemoryOIDCPublisherService(oidc_services.OIDCPublisherService):
    keysets = {}

    def _store_keyset(self, issuer_url, keys):
        self.keysets[issuer_url] = keys

    def _get_keyset(self, issuer_url):
        return self.keysets.get(issuer_url, {}), False


@pytest.mark.usefixtures("_enable_all_oidc_providers")
@pytest.mark.parametrize("audience", ["pypi", "testpypi"])
@responses.activate
def test_buildkite_publisher_mints_api_token(
    webtest, app_config_dbsession_from_env, monkeypatch, mockredis, audience
):
    """Exchange pins IDs on first use and rejects missing claims and replay."""
    monkeypatch.setattr(oidc_services.redis, "StrictRedis", mockredis)
    monkeypatch.setitem(
        app_config_dbsession_from_env.registry.settings,
        "warehouse.oidc.audience",
        audience,
    )
    publisher = BuildkitePublisherFactory.create(
        organization_slug="acme",
        pipeline_slug="widgets",
        build_branch="main",
        step_key="publish",
        buildkite_organization_id=None,
        pipeline_id=None,
        projects=[ProjectFactory.create(name="buildkite-project")],
    )
    db = webtest.extra_environ["warehouse.db_session"]
    now = int(time.time())
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"alg": "RS256", "kid": "buildkite-test", "use": "sig"})

    jwks_url = f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/jwks"
    responses.add(
        responses.GET,
        f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/openid-configuration",
        json={"jwks_uri": jwks_url},
    )
    responses.add(responses.GET, jwks_url, json={"keys": [public_jwk]})

    token_claims = {
        "iss": BUILDKITE_OIDC_ISSUER_URL,
        "sub": (
            "organization:acme:pipeline:widgets:ref:refs/heads/main:"
            "commit:abc123:step:publish"
        ),
        "aud": audience,
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "jti": "buildkite-first-publish",
        "organization_slug": "acme",
        "organization_id": "00000000-1111-2222-3333-444444444444",
        "pipeline_slug": "widgets",
        "pipeline_id": "11111111-2222-3333-4444-555555555555",
        "build_number": 42,
        "build_branch": "main",
        "build_commit": "abc123",
        "step_key": "publish",
        "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "agent_id": "ffffffff-1111-2222-3333-444444444444",
        "runner_environment": "buildkite-hosted",
        "build_source": "webhook",
    }
    oidc_token = jwt.encode(
        token_claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "buildkite-test"},
    )

    service_registry = app_config_dbsession_from_env.registry.getUtility(
        IServiceRegistry
    )
    original_factory = service_registry.find_factory(
        oidc_interfaces.IOIDCPublisherService, name="buildkite"
    )
    service_factory = oidc_services.OIDCPublisherServiceFactory(
        publisher="buildkite",
        issuer_url=BUILDKITE_OIDC_ISSUER_URL,
        service_class=_InMemoryOIDCPublisherService,
    )
    service_registry.register_factory(
        ProxyFactory(service_factory),
        oidc_interfaces.IOIDCPublisherService,
        name="buildkite",
    )
    _InMemoryOIDCPublisherService.keysets.clear()
    try:
        pending_fields = {
            "project_name": "pending-buildkite-project",
            "organization_slug": "acme",
            "pipeline_slug": "widgets",
            "build_branch": "main",
            "step_key": "publish",
            "buildkite_organization_id": None,
            "pipeline_id": None,
        }
        # A recycled slug must not attach a new project to an old pinned identity,
        # even if the token exchange itself would subsequently be rejected.
        for attribute in ("buildkite_organization_id", "pipeline_id"):
            pending = PendingBuildkitePublisherFactory.create(**pending_fields)
            setattr(publisher, attribute, "previous-owner-id")
            db.flush()
            rejected = webtest.post_json(
                "/_/oidc/mint-token",
                {"token": oidc_token},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            assert "does not match" in rejected.json["errors"][0]["description"]
            assert (
                db.query(Project).filter_by(name="pending-buildkite-project").count()
                == 0
            )
            assert db.get(PendingBuildkitePublisher, pending.id) is pending
            db.refresh(publisher)
            assert [project.name for project in publisher.projects] == [
                "buildkite-project"
            ]
            setattr(publisher, attribute, None)
            db.delete(pending)
            db.flush()

        # Neither missing nor empty identity claims may establish the pins.
        for claim in ("organization_id", "pipeline_id", "jti"):
            for missing in (True, False):
                invalid_claims = token_claims | {claim: ""}
                if missing:
                    invalid_claims.pop(claim)
                invalid_token = jwt.encode(
                    invalid_claims,
                    private_key,
                    algorithm="RS256",
                    headers={"kid": "buildkite-test"},
                )
                invalid_response = webtest.post_json(
                    "/_/oidc/mint-token",
                    {"token": invalid_token},
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                )
                assert claim in invalid_response.json["errors"][0]["description"]

        db.refresh(publisher)
        assert publisher.buildkite_organization_id is None
        assert publisher.pipeline_id is None

        pending = PendingBuildkitePublisherFactory.create(**pending_fields)
        response = webtest.post_json(
            "/_/oidc/mint-token", {"token": oidc_token}, status=HTTPStatus.OK
        )
        assert db.get(PendingBuildkitePublisher, pending.id) is None
        db.refresh(publisher)
        assert {project.name for project in publisher.projects} == {
            "buildkite-project",
            "pending-buildkite-project",
        }
        replay_response = webtest.post_json(
            "/_/oidc/mint-token",
            {"token": oidc_token},
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
        assert replay_response.json["errors"][0]["code"] == "invalid-reuse-token"
    finally:
        service_registry.register_factory(
            original_factory, oidc_interfaces.IOIDCPublisherService, name="buildkite"
        )

    assert response.json["success"] is True
    assert response.json["token"].startswith("pypi-")
    assert response.json["expires"] > now
    db.refresh(publisher)
    assert publisher.buildkite_organization_id == token_claims["organization_id"]
    assert publisher.pipeline_id == token_claims["pipeline_id"]

    missing_claims = token_claims.copy()
    missing_claims.pop("organization_id")
    missing_token = jwt.encode(
        missing_claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "buildkite-test"},
    )
    missing_response = webtest.post_json(
        "/_/oidc/mint-token",
        {"token": missing_token},
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    assert (
        "Missing claim 'organization_id'"
        in missing_response.json["errors"][0]["description"]
    )

    mismatched_claims = token_claims | {"pipeline_id": "different-pipeline"}
    mismatched_token = jwt.encode(
        mismatched_claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "buildkite-test"},
    )
    mismatched_response = webtest.post_json(
        "/_/oidc/mint-token",
        {"token": mismatched_token},
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    assert "does not match" in mismatched_response.json["errors"][0]["description"]
    assert [call.request.url for call in responses.calls] == [
        f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/openid-configuration",
        jwks_url,
    ]
