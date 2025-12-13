# SPDX-License-Identifier: Apache-2.0

import time

from datetime import datetime
from typing import TypedDict, cast

import jwt
import sentry_sdk

from pydantic import BaseModel, StrictStr, ValidationError
from pyramid.httpexceptions import HTTPException, HTTPForbidden
from pyramid.request import Request
from pyramid.view import view_config

from warehouse.email import send_environment_ignored_in_trusted_publisher_email
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import DatabaseMacaroonService
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.errors import InvalidPublisherError, ReusedTokenError
from warehouse.oidc.interfaces import IOIDCPublisherService, SignedClaims
from warehouse.oidc.models import GitHubPublisher, OIDCPublisher, PendingOIDCPublisher
from warehouse.oidc.models.gitlab import GitLabPublisher
from warehouse.oidc.services import OIDCPublisherService
from warehouse.oidc.utils import (
    OIDC_ISSUER_ADMIN_FLAGS,
    OIDC_ISSUER_SERVICE_NAMES,
    lookup_custom_issuer_type,
)
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import ProjectFactory
from warehouse.rate_limiting.interfaces import IRateLimiter


class Error(TypedDict):
    code: str
    description: str


class JsonResponse(TypedDict, total=False):
    message: str | None
    errors: list[Error] | None
    token: StrictStr | None
    # This value is used to communicate the minted token's expiration
    # time to the user. It is not used to determine the expiration,
    # changing this field does not change the token's expiration time.
    expires: int | None
    success: bool | None


class TokenPayload(BaseModel):
    token: StrictStr


def _ratelimiters(request: Request) -> dict[str, IRateLimiter]:
    return {
        "user.oidc": request.find_service(
            IRateLimiter, name="user_oidc.publisher.register"
        ),
        "ip.oidc": request.find_service(
            IRateLimiter, name="ip_oidc.publisher.register"
        ),
    }


def _invalid(errors: list[Error], request: Request) -> JsonResponse:
    request.response.status = 422

    return {
        "message": "Token request failed",
        "errors": errors,
    }


@view_config(
    route_name="oidc.audience",
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def oidc_audience(request: Request):
    if request.flags.disallow_oidc():
        return HTTPForbidden(
            json={"message": "Trusted publishing functionality not enabled"}
        )

    audience: str = request.registry.settings["warehouse.oidc.audience"]
    return {"audience": audience}


@view_config(
    route_name="oidc.github.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
)
@view_config(
    route_name="oidc.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
)
def mint_token_from_oidc(request: Request):
    try:
        payload = TokenPayload.model_validate_json(request.body)
        unverified_jwt = payload.token
    except ValidationError as exc:
        return _invalid(
            errors=[{"code": "invalid-payload", "description": str(exc)}],
            request=request,
        )

    # We currently have an **unverified** JWT. To verify it, we need to
    # know which OIDC service's keyring to check it against.
    # To do this, we gingerly peek into the unverified claims and
    # use the `iss` to key into the right `OIDCPublisherService`.
    try:
        unverified_claims = jwt.decode(
            unverified_jwt, options=dict(verify_signature=False)
        )
        unverified_issuer: str = unverified_claims["iss"]
    except Exception as e:
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment("warehouse.oidc.mint_token_from_oidc.malformed_jwt")

        # We expect only PyJWTError and KeyError; anything else indicates
        # an abstraction leak in jwt that we'll log for upstream reporting.
        if not isinstance(e, (jwt.PyJWTError, KeyError)):
            with sentry_sdk.new_scope() as scope:
                scope.fingerprint = [e]
                sentry_sdk.capture_message(f"jwt.decode raised generic error: {e}")

        return _invalid(
            errors=[{"code": "invalid-payload", "description": "malformed JWT"}],
            request=request,
        )

    # Associate the given issuer claim with Warehouse's OIDCPublisherService.
    # First, try the standard issuers
    service_name = OIDC_ISSUER_SERVICE_NAMES.get(unverified_issuer)
    # If not in global mapping, check for organization-specific custom issuer
    if not service_name:
        service_name = lookup_custom_issuer_type(request.db, unverified_issuer)
    if not service_name:
        request.metrics.increment(
            "warehouse.oidc.mint_token_from_oidc.unknown_issuer",
            tags=[f"issuer_url:{unverified_issuer}"],
        )
        return _invalid(
            errors=[
                {
                    "code": "invalid-payload",
                    "description": "unknown trusted publishing issuer",
                }
            ],
            request=request,
        )

    if request.flags.disallow_oidc(OIDC_ISSUER_ADMIN_FLAGS.get(unverified_issuer)):
        return _invalid(
            errors=[
                {
                    "code": "not-enabled",
                    "description": f"{service_name} trusted publishing functionality not enabled",  # noqa: E501
                }
            ],
            request=request,
        )

    oidc_service: OIDCPublisherService = request.find_service(
        IOIDCPublisherService, name=service_name
    )

    return mint_token(oidc_service, unverified_jwt, unverified_issuer, request)


def mint_token(
    oidc_service: OIDCPublisherService,
    unverified_jwt: str,
    unverified_issuer: str,
    request: Request,
) -> JsonResponse:
    claims = oidc_service.verify_jwt_signature(unverified_jwt, unverified_issuer)
    if not claims:
        return _invalid(
            errors=[
                {"code": "invalid-token", "description": "malformed or invalid token"}
            ],
            request=request,
        )

    # First, try to find a pending publisher.
    try:
        pending_publisher = oidc_service.find_publisher(claims, pending=True)
        factory = ProjectFactory(request)

        if isinstance(pending_publisher, PendingOIDCPublisher):
            # If the project already exists, this pending publisher is no longer
            # valid and needs to be removed.
            # NOTE: This is mostly a sanity check, since we dispose of invalidated
            # pending publishers below.
            if pending_publisher.project_name in factory:
                request.db.delete(pending_publisher)
                return _invalid(
                    errors=[
                        {
                            "code": "invalid-pending-publisher",
                            "description": "valid token, but project already exists",
                        }
                    ],
                    request=request,
                )

            # Try creating the new project
            project_service = request.find_service(IProjectService)
            try:
                new_project = project_service.create_project(
                    pending_publisher.project_name,
                    pending_publisher.added_by,
                    request,
                    creator_is_owner=pending_publisher.organization_id is None,
                    ratelimited=False,
                    organization_id=pending_publisher.organization_id,
                )
            except HTTPException as exc:
                return _invalid(
                    errors=[{"code": "invalid-payload", "description": str(exc)}],
                    request=request,
                )

            # Reify the pending publisher against the newly created project
            reified_publisher = oidc_service.reify_pending_publisher(
                pending_publisher, new_project
            )
            request.db.flush()  # To get the reified_publisher.id
            new_project.record_event(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=request,
                additional={
                    "publisher": reified_publisher.publisher_name,
                    "id": str(reified_publisher.id),
                    "specifier": str(reified_publisher),
                    "url": reified_publisher.publisher_url(),
                    "submitted_by": "OpenID created token",
                    "reified_from_pending_publisher": True,
                    "constrained_from_existing_publisher": False,
                },
            )

            # Successfully converting a pending publisher into a normal publisher
            # is a positive signal, so we reset the associated ratelimits.
            ratelimiters = _ratelimiters(request)
            ratelimiters["user.oidc"].clear(pending_publisher.added_by.id)
            ratelimiters["ip.oidc"].clear(request.remote_addr)
    except InvalidPublisherError:
        # If the claim set isn't valid for a pending publisher, it's OK, we
        # will try finding a regular publisher
        pass

    # We either don't have a pending OIDC publisher, or we *did*
    # have one and we've just converted it. Either way, look for a full publisher
    # to actually do the macaroon minting with.
    try:
        publisher = oidc_service.find_publisher(claims, pending=False)
        # NOTE: assert to persuade mypy of the correct type here.
        assert isinstance(publisher, OIDCPublisher)
    except ReusedTokenError:
        return _invalid(
            errors=[
                {
                    "code": "invalid-reuse-token",
                    "description": "invalid token: already used",
                }
            ],
            request=request,
        )
    except InvalidPublisherError as e:
        return _invalid(
            errors=[
                {
                    "code": "invalid-publisher",
                    "description": f"valid token, but no corresponding publisher ({e})",
                }
            ],
            request=request,
        )

    # At this point, we've verified that the given JWT is valid for the given
    # project. All we need to do is mint a new token.
    # NOTE: For OIDC-minted API tokens, the Macaroon's description string
    # is purely an implementation detail and is not displayed to the user.
    macaroon_service: DatabaseMacaroonService = request.find_service(
        IMacaroonService, context=None
    )
    not_before = int(time.time())
    expires_at = not_before + 900
    serialized, dm = macaroon_service.create_macaroon(
        request.domain,
        (
            f"OpenID token: {str(publisher)} "
            f"({datetime.fromtimestamp(not_before).isoformat()})"
        ),
        [
            caveats.OIDCPublisher(
                oidc_publisher_id=str(publisher.id),
            ),
            caveats.ProjectID(project_ids=[str(p.id) for p in publisher.projects]),
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_publisher_id=str(publisher.id),
        additional={"oidc": publisher.stored_claims(claims)},
    )

    # We have used the given JWT to mint a new token. Let now store it to prevent
    # its reuse if the claims contain a JTI. Of note, exp is coming from a trusted
    # source here, so we don't validate it
    if jwt_identifier := claims.get("jti"):
        expiration = cast(int, claims.get("exp"))
        oidc_service.store_jwt_identifier(jwt_identifier, expiration)

    for project in publisher.projects:
        project.record_event(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            request=request,
            additional={
                "expires": expires_at,
                "publisher_name": publisher.publisher_name,
                "publisher_url": publisher.publisher_url(),
                "reusable_workflow_used": is_from_reusable_workflow(publisher, claims),
            },
        )

    # Send a warning email to the owners of the project using the Trusted Publisher if
    # the TP has no environment configured but the OIDC claims contain one.
    # The email contains a link to change the TP so that it only accepts the
    # environment seen in the current OIDC claims.
    #
    # Note: currently we only send the email if the Trusted Publisher is used in only
    # a single project, since multiple projects using the same TP might mean they don't
    # use a single environment.
    if len(publisher.projects) == 1 and should_send_environment_warning_email(
        publisher, claims
    ):
        send_environment_ignored_in_trusted_publisher_email(
            request,
            set(publisher.projects[0].owners),
            project_name=publisher.projects[0].name,
            publisher=publisher,
            environment_name=claims["environment"],
        )

    # NOTE: This is for temporary metrics collection of GitHub Trusted Publishers
    # that use reusable workflows. Since support for reusable workflows is accidental
    # and not correctly implemented, we need to understand how widely it's being
    # used before changing its behavior.
    # ref: https://github.com/pypi/warehouse/pull/16364
    if claims and is_from_reusable_workflow(publisher, claims):
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment("warehouse.oidc.mint_token.github_reusable_workflow")

    return {"success": True, "token": serialized, "expires": expires_at}


def is_from_reusable_workflow(
    publisher: OIDCPublisher | None, claims: SignedClaims
) -> bool:
    """Detect if the claims are originating from a reusable workflow."""
    if not isinstance(publisher, GitHubPublisher):
        return False

    job_workflow_ref = claims.get("job_workflow_ref")
    workflow_ref = claims.get("workflow_ref")

    # When using reusable workflows, `job_workflow_ref` contains the reusable (
    # called) workflow and `workflow_ref` contains the parent (caller) workflow.
    # With non-reusable workflows they are the same, so we count reusable
    # workflows by checking if they are different.
    return bool(job_workflow_ref and workflow_ref and job_workflow_ref != workflow_ref)


def should_send_environment_warning_email(
    publisher: OIDCPublisher, claims: SignedClaims
) -> bool:
    """
    Determine if the claims contain an environment but the publisher doesn't

    If the publisher does not have an environment configured but the claims
    contain one, it means the project can easily improve security by constraining
    the Trusted Publisher to only that environment.

    This currently only applies to GitHub and GitLab publishers.
    """
    if not isinstance(publisher, (GitHubPublisher, GitLabPublisher)):
        return False

    claims_env = claims.get("environment")

    return publisher.environment == "" and claims_env is not None and claims_env != ""
