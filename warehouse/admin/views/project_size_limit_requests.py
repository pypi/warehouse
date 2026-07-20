# SPDX-License-Identifier: Apache-2.0

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.email import (
    send_project_size_limit_request_approved_email,
    send_project_size_limit_request_declined_email,
)
from warehouse.events.tags import EventTag
from warehouse.packaging.models import (
    Project,
    ProjectSizeLimitRequest,
    ProjectSizeLimitRequestStatus,
)
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.project_size_limit_request.list",
    renderer="warehouse.admin:templates/admin/project_size_limit_requests/list.html",
    permission=Permissions.AdminProjectsRead,
    uses_session=True,
)
def project_size_limit_requests_list(request):
    q = request.params.get("q", "")
    try:
        terms = shlex.split(q)
    except ValueError:
        raise HTTPBadRequest("Invalid query.") from None

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    size_limit_requests_query = request.db.query(ProjectSizeLimitRequest).order_by(
        ProjectSizeLimitRequest.submitted.desc()
    )

    if q:
        filters: list = []
        for term in terms:
            # Examples:
            # - search individual words or "whole phrase" in any field
            # - project:foo
            # - name:foo
            # - by:someuser
            # - user:someuser
            # - is:submitted
            # - is:approved
            # - is:declined
            try:
                field, value = term.lower().split(":", 1)
            except ValueError:
                field, value = "", term
            if field in {"project", "name"}:
                filters.append(
                    ProjectSizeLimitRequest.project.has(
                        or_(
                            Project.name.ilike(f"%{value}%"),
                            Project.normalized_name.ilike(f"%{value}%"),
                        )
                    )
                )
            elif field in {"by", "user", "requester"}:
                filters.append(
                    ProjectSizeLimitRequest.submitted_by.has(
                        User.username.ilike(f"%{value}%")
                    )
                )
            elif field == "is" and value in ProjectSizeLimitRequestStatus:
                filters.append(ProjectSizeLimitRequest.status == value)
            else:
                filters.append(
                    or_(
                        ProjectSizeLimitRequest.project.has(
                            or_(
                                Project.name.ilike(f"%{term}%"),
                                Project.normalized_name.ilike(f"%{term}%"),
                            )
                        ),
                        ProjectSizeLimitRequest.submitted_by.has(
                            User.username.ilike(f"%{term}%")
                        ),
                    )
                )
        for term_filter in filters:
            size_limit_requests_query = size_limit_requests_query.filter(term_filter)

    size_limit_requests_query = size_limit_requests_query.options(
        joinedload(ProjectSizeLimitRequest.project),
        joinedload(ProjectSizeLimitRequest.submitted_by),
    )

    size_limit_requests = SQLAlchemyORMPage(
        size_limit_requests_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {
        "project_size_limit_requests": size_limit_requests,
        "query": q,
        "terms": terms,
    }


@view_config(
    route_name="admin.project_size_limit_request.detail",
    renderer="warehouse.admin:templates/admin/project_size_limit_requests/detail.html",
    permission=Permissions.AdminProjectsRead,
    uses_session=True,
)
def project_size_limit_request_detail(request):
    size_limit_request = request.db.get(
        ProjectSizeLimitRequest, request.matchdict["request_id"]
    )
    if size_limit_request is None:
        raise HTTPNotFound

    return {"size_limit_request": size_limit_request}


def _get_reviewable_request(request):
    size_limit_request = request.db.get(
        ProjectSizeLimitRequest, request.matchdict["request_id"]
    )
    if size_limit_request is None:
        raise HTTPNotFound

    if size_limit_request.status != ProjectSizeLimitRequestStatus.Submitted:
        request.session.flash("This request has already been reviewed", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project_size_limit_request.detail",
                request_id=size_limit_request.id,
            )
        )

    return size_limit_request


def _get_review_message(request, size_limit_request):
    message = request.params.get("message") or None

    if message is not None and len(message) > 4096:
        request.session.flash("Message must be 4096 characters or less", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project_size_limit_request.detail",
                request_id=size_limit_request.id,
            )
        )

    return message


@view_config(
    route_name="admin.project_size_limit_request.approve",
    require_methods=["POST"],
    permission=Permissions.AdminProjectsSetLimit,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def project_size_limit_request_approve(request):
    size_limit_request = _get_reviewable_request(request)
    project = size_limit_request.project

    old_total_size_limit = project.total_size_limit
    project.total_size_limit = size_limit_request.requested_limit

    message = _get_review_message(request, size_limit_request)

    size_limit_request.status = ProjectSizeLimitRequestStatus.Approved
    size_limit_request.admin_message = message

    send_project_size_limit_request_approved_email(
        request,
        size_limit_request.submitted_by,
        project_name=project.name,
        requested_limit=project.total_size_limit,
        message=message or "",
    )

    project.record_event(
        tag=EventTag.Project.ProjectSetTotalSizeLimit,
        request=request,
        additional={
            "old_total_size_limit": old_total_size_limit,
            "new_total_size_limit": project.total_size_limit,
            "actor": request.user.username,
        },
    )
    project.record_event(
        tag=EventTag.Project.ProjectSizeLimitRequestApproved,
        request=request,
        additional={"actor": request.user.username},
    )

    request.session.flash(
        f"Approved the size limit increase request for {project.name!r}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "admin.project_size_limit_request.detail",
            request_id=size_limit_request.id,
        )
    )


@view_config(
    route_name="admin.project_size_limit_request.decline",
    require_methods=["POST"],
    permission=Permissions.AdminProjectsSetLimit,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def project_size_limit_request_decline(request):
    size_limit_request = _get_reviewable_request(request)
    project = size_limit_request.project

    message = _get_review_message(request, size_limit_request)

    size_limit_request.status = ProjectSizeLimitRequestStatus.Declined
    size_limit_request.admin_message = message

    send_project_size_limit_request_declined_email(
        request,
        size_limit_request.submitted_by,
        project_name=project.name,
        message=message or "",
    )

    project.record_event(
        tag=EventTag.Project.ProjectSizeLimitRequestDeclined,
        request=request,
        additional={"actor": request.user.username},
    )

    request.session.flash(
        f"Declined the size limit increase request for {project.name!r}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "admin.project_size_limit_request.detail",
            request_id=size_limit_request.id,
        )
    )
