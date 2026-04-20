# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import http
import typing

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPNotFound,
    HTTPTooManyRequests,
)
from webob.multidict import MultiDict

from warehouse.admin.flags import AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.email import (
    send_trusted_publisher_added_email,
    send_trusted_publisher_removed_email,
)
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.oidc.forms import (
    ActiveStatePublisherForm,
    GitHubPublisherForm,
    GitLabPublisherForm,
    GooglePublisherForm,
)
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
)
from warehouse.rate_limiting import IRateLimiter

from .echo import api_v0_view_config

if typing.TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.packaging.models import Project


def _multidict_from_json(data: dict) -> MultiDict:
    md = MultiDict()
    for key, value in data.items():
        if value is not None:
            md.add(key, value if isinstance(value, str) else str(value))
    return md


def _check_ratelimits(request: Request) -> None:
    user_limiter = request.find_service(
        IRateLimiter, name="user_oidc.publisher.register"
    )
    ip_limiter = request.find_service(
        IRateLimiter, name="ip_oidc.publisher.register"
    )

    if not user_limiter.test(request.user.id):
        raise TooManyOIDCRegistrations(
            resets_in=user_limiter.resets_in(request.user.id)
        )
    if not ip_limiter.test(request.remote_addr):
        raise TooManyOIDCRegistrations(
            resets_in=ip_limiter.resets_in(request.remote_addr)
        )


def _hit_ratelimits(request: Request) -> None:
    request.find_service(
        IRateLimiter, name="user_oidc.publisher.register"
    ).hit(request.user.id)
    request.find_service(
        IRateLimiter, name="ip_oidc.publisher.register"
    ).hit(request.remote_addr)


def _publisher_as_dict(publisher: OIDCPublisher) -> dict:
    return {
        "id": str(publisher.id),
        "publisher_name": publisher.publisher_name,
        "publisher_url": publisher.publisher_url(),
        "specifier": str(publisher),
    }


@api_v0_view_config(
    route_name="api.projects.trusted_publishers",
    permission=Permissions.APITrustedPublishersManage,
    require_methods=["GET"],
)
def api_get_trusted_publishers(project: Project, request: Request) -> dict:
    return {
        "trusted_publishers": [
            _publisher_as_dict(p) for p in project.oidc_publishers
        ]
    }


@api_v0_view_config(
    route_name="api.projects.trusted_publishers",
    permission=Permissions.APITrustedPublishersManage,
    require_methods=["POST"],
)
def api_add_trusted_publisher(project: Project, request: Request) -> dict:
    metrics = request.find_service(IMetricsService, context=None)

    if request.flags.disallow_oidc():
        raise HTTPForbidden(
            json={
                "error": (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                )
            }
        )

    data = request.json_body
    publisher_type = data.get("publisher", "")

    if publisher_type == "github":
        if request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITHUB_OIDC):
            raise HTTPForbidden(
                json={
                    "error": (
                        "GitHub-based trusted publishing is temporarily disabled. "
                        "See https://pypi.org/help#admin-intervention for details."
                    )
                }
            )

        metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitHub"]
        )

        try:
            _check_ratelimits(request)
        except TooManyOIDCRegistrations as exc:
            metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitHub"]
            )
            raise HTTPTooManyRequests(
                json={
                    "error": (
                        "Too many trusted publisher registrations. Try again later."
                    )
                },
                headers={
                    "Retry-After": str(int(exc.resets_in.total_seconds()))
                },
            )

        _hit_ratelimits(request)

        form = GitHubPublisherForm(
            _multidict_from_json(data),
            api_token=request.registry.settings.get("github.token"),
        )

        if not form.validate():
            raise HTTPBadRequest(json={"errors": form.errors})

        publisher = (
            request.db.query(GitHubPublisher)
            .filter(
                GitHubPublisher.repository_name == form.repository.data,
                GitHubPublisher.repository_owner == form.normalized_owner,
                GitHubPublisher.workflow_filename == form.workflow_filename.data,
                GitHubPublisher.environment == form.normalized_environment,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GitHubPublisher(
                repository_name=form.repository.data,
                repository_owner=form.normalized_owner,
                repository_owner_id=form.owner_id,
                workflow_filename=form.workflow_filename.data,
                environment=form.normalized_environment,
            )
            request.db.add(publisher)

        publisher_tag = "GitHub"

    elif publisher_type == "gitlab":
        if request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITLAB_OIDC):
            raise HTTPForbidden(
                json={
                    "error": (
                        "GitLab-based trusted publishing is temporarily disabled. "
                        "See https://pypi.org/help#admin-intervention for details."
                    )
                }
            )

        metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitLab"]
        )

        try:
            _check_ratelimits(request)
        except TooManyOIDCRegistrations as exc:
            metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitLab"]
            )
            raise HTTPTooManyRequests(
                json={
                    "error": (
                        "Too many trusted publisher registrations. Try again later."
                    )
                },
                headers={
                    "Retry-After": str(int(exc.resets_in.total_seconds()))
                },
            )

        _hit_ratelimits(request)

        _gl_issuers = GitLabPublisher.get_available_issuer_urls(
            organization=project.organization
        )
        form = GitLabPublisherForm(
            _multidict_from_json(data),
            issuer_url_choices=_gl_issuers,
        )

        if not form.validate():
            raise HTTPBadRequest(json={"errors": form.errors})

        publisher = (
            request.db.query(GitLabPublisher)
            .filter(
                GitLabPublisher.namespace == form.namespace.data,
                GitLabPublisher.project == form.project.data,
                GitLabPublisher.workflow_filepath == form.workflow_filepath.data,
                GitLabPublisher.environment == form.normalized_environment,
                GitLabPublisher.issuer_url == form.issuer_url.data,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GitLabPublisher(
                namespace=form.namespace.data,
                project=form.project.data,
                workflow_filepath=form.workflow_filepath.data,
                environment=form.normalized_environment,
                issuer_url=form.issuer_url.data,
            )
            request.db.add(publisher)

        publisher_tag = "GitLab"

    elif publisher_type == "google":
        if request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GOOGLE_OIDC):
            raise HTTPForbidden(
                json={
                    "error": (
                        "Google-based trusted publishing is temporarily disabled. "
                        "See https://pypi.org/help#admin-intervention for details."
                    )
                }
            )

        metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:Google"]
        )

        try:
            _check_ratelimits(request)
        except TooManyOIDCRegistrations as exc:
            metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:Google"]
            )
            raise HTTPTooManyRequests(
                json={
                    "error": (
                        "Too many trusted publisher registrations. Try again later."
                    )
                },
                headers={
                    "Retry-After": str(int(exc.resets_in.total_seconds()))
                },
            )

        _hit_ratelimits(request)

        form = GooglePublisherForm(_multidict_from_json(data))

        if not form.validate():
            raise HTTPBadRequest(json={"errors": form.errors})

        publisher = (
            request.db.query(GooglePublisher)
            .filter(
                GooglePublisher.email == form.email.data,
                GooglePublisher.sub == form.sub.data,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GooglePublisher(
                email=form.email.data,
                sub=form.sub.data,
            )
            request.db.add(publisher)

        publisher_tag = "Google"

    elif publisher_type == "activestate":
        if request.flags.disallow_oidc(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC):
            raise HTTPForbidden(
                json={
                    "error": (
                        "ActiveState-based trusted publishing is temporarily disabled. "
                        "See https://pypi.org/help#admin-intervention for details."
                    )
                }
            )

        metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:ActiveState"]
        )

        try:
            _check_ratelimits(request)
        except TooManyOIDCRegistrations as exc:
            metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=["publisher:ActiveState"],
            )
            raise HTTPTooManyRequests(
                json={
                    "error": (
                        "Too many trusted publisher registrations. Try again later."
                    )
                },
                headers={
                    "Retry-After": str(int(exc.resets_in.total_seconds()))
                },
            )

        _hit_ratelimits(request)

        form = ActiveStatePublisherForm(_multidict_from_json(data))

        if not form.validate():
            raise HTTPBadRequest(json={"errors": form.errors})

        publisher = (
            request.db.query(ActiveStatePublisher)
            .filter(
                ActiveStatePublisher.organization == form.organization.data,
                ActiveStatePublisher.activestate_project_name == form.project.data,
                ActiveStatePublisher.actor_id == form.actor_id,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = ActiveStatePublisher(
                organization=form.organization.data,
                activestate_project_name=form.project.data,
                actor=form.actor.data,
                actor_id=form.actor_id,
            )
            request.db.add(publisher)

        publisher_tag = "ActiveState"

    else:
        raise HTTPBadRequest(
            json={"error": f"Unknown publisher type: {publisher_type!r}"}
        )

    if publisher in project.oidc_publishers:
        raise HTTPConflict(
            json={
                "error": f"{publisher} is already registered with {project.name}"
            }
        )

    for user in project.users:
        send_trusted_publisher_added_email(
            request,
            user,
            project_name=project.name,
            publisher=publisher,
        )

    project.oidc_publishers.append(publisher)

    project.record_event(
        tag=EventTag.Project.OIDCPublisherAdded,
        request=request,
        additional={
            "publisher": publisher.publisher_name,
            "id": str(publisher.id),
            "specifier": str(publisher),
            "url": publisher.publisher_url(),
            "submitted_by": request.user.username,
            "reified_from_pending_publisher": False,
            "constrained_from_existing_publisher": False,
        },
    )

    metrics.increment(
        "warehouse.oidc.add_publisher.ok", tags=[f"publisher:{publisher_tag}"]
    )

    request.response.status = http.HTTPStatus.CREATED
    return {"trusted_publisher": _publisher_as_dict(publisher)}


@api_v0_view_config(
    route_name="api.projects.trusted_publisher",
    permission=Permissions.APITrustedPublishersManage,
    require_methods=["DELETE"],
)
def api_delete_trusted_publisher(project: Project, request: Request) -> dict:
    metrics = request.find_service(IMetricsService, context=None)

    if request.flags.disallow_oidc():
        raise HTTPForbidden(
            json={
                "error": (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                )
            }
        )

    metrics.increment("warehouse.oidc.delete_publisher.attempt")

    publisher_id = request.matchdict.get("publisher_id")
    publisher = request.db.get(OIDCPublisher, publisher_id)

    if publisher is None or publisher not in project.oidc_publishers:
        return HTTPNotFound(
            json={"error": "Publisher not found for this project"}
        )

    for user in project.users:
        send_trusted_publisher_removed_email(
            request,
            user,
            project_name=project.name,
            publisher=publisher,
        )

    project.record_event(
        tag=EventTag.Project.OIDCPublisherRemoved,
        request=request,
        additional={
            "publisher": publisher.publisher_name,
            "id": str(publisher.id),
            "specifier": str(publisher),
            "url": publisher.publisher_url(),
            "submitted_by": request.user.username,
        },
    )

    project.oidc_publishers.remove(publisher)
    if len(publisher.projects) == 0:
        request.db.delete(publisher)

    metrics.increment(
        "warehouse.oidc.delete_publisher.ok",
        tags=[f"publisher:{publisher.publisher_name}"],
    )

    return {"message": f"Removed trusted publisher from {project.name}"}
