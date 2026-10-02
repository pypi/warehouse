# SPDX-License-Identifier: Apache-2.0

"""Admin Views for Vulnerability records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import ColumnElement, Select, delete, func, or_, select
from sqlalchemy.orm import Query, selectinload

from warehouse.authnz import Permissions
from warehouse.integrations.vulnerabilities.models import (
    ReleaseVulnerability,
    VulnerabilityRecord,
)
from warehouse.packaging.models import Release
from warehouse.utils.paginate import paginate_url_factory

if TYPE_CHECKING:
    from pyramid.request import Request

BULK_DELETE_LIMIT = 5000


def _filter_predicate(q: str) -> ColumnElement[bool]:
    # Honor explicit `%` wildcards, otherwise wrap for a substring match.
    pattern = q if "%" in q else f"%{q}%"
    return or_(
        VulnerabilityRecord.id.ilike(pattern),
        VulnerabilityRecord.source.ilike(pattern),
        func.array_to_string(VulnerabilityRecord.aliases, ",").ilike(pattern),
    )


def _apply_filter(
    stmt: Select[Any] | Query[Any], q: str | None
) -> Select[Any] | Query[Any]:
    return stmt if not q else stmt.filter(_filter_predicate(q))


def _get_or_404(request: Request, source: str, vuln_id: str) -> VulnerabilityRecord:
    stmt = (
        select(VulnerabilityRecord)
        .where(
            VulnerabilityRecord.source == source,
            VulnerabilityRecord.id == vuln_id,
        )
        .options(
            selectinload(VulnerabilityRecord.releases).selectinload(Release.project)
        )
    )
    record = request.db.scalars(stmt).unique().one_or_none()
    if record is None:
        raise HTTPNotFound
    return record


@view_config(
    route_name="admin.vulnerabilities.list",
    renderer="warehouse.admin:templates/admin/vulnerabilities/list.html",
    permission=Permissions.AdminVulnerabilitiesRead,
    request_method="GET",
    uses_session=True,
)
def vulnerability_list(request: Request) -> dict[str, Any]:
    q: str | None = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    # paginate_sqlalchemy's SqlalchemyOrmPage needs a legacy Query; everywhere
    # else in this view we use ORM 2.0 `select()`.
    page_query = _apply_filter(request.db.query(VulnerabilityRecord), q).order_by(
        VulnerabilityRecord.source, VulnerabilityRecord.id
    )

    vulnerabilities = SQLAlchemyORMPage(
        page_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    keys = [(v.source, v.id) for v in vulnerabilities.items]
    counts: dict[tuple[str, str], int] = {}
    if keys:
        sources = {source for source, _ in keys}
        ids = {vuln_id for _, vuln_id in keys}
        count_stmt = (
            select(
                ReleaseVulnerability.vulnerability_source,
                ReleaseVulnerability.vulnerability_id,
                func.count(ReleaseVulnerability.release_id),
            )
            .where(
                ReleaseVulnerability.vulnerability_source.in_(sources),
                ReleaseVulnerability.vulnerability_id.in_(ids),
            )
            .group_by(
                ReleaseVulnerability.vulnerability_source,
                ReleaseVulnerability.vulnerability_id,
            )
        )
        counts = {
            (source, vuln_id): count
            for source, vuln_id, count in request.db.execute(count_stmt).all()
        }

    return {
        "vulnerabilities": vulnerabilities,
        "release_counts": counts,
        "query": q,
    }


@view_config(
    route_name="admin.vulnerabilities.detail",
    renderer="warehouse.admin:templates/admin/vulnerabilities/detail.html",
    permission=Permissions.AdminVulnerabilitiesRead,
    request_method="GET",
    uses_session=True,
)
def vulnerability_detail(request: Request) -> dict[str, Any]:
    record = _get_or_404(request, request.matchdict["source"], request.matchdict["id"])
    releases = sorted(
        record.releases, key=lambda r: (r.project.name.lower(), r.version)
    )
    return {"vulnerability": record, "releases": releases}


@view_config(
    route_name="admin.vulnerabilities.detail.delete",
    permission=Permissions.AdminVulnerabilitiesWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def vulnerability_delete(request: Request) -> HTTPSeeOther:
    source: str = request.matchdict["source"]
    vuln_id: str = request.matchdict["id"]
    record = _get_or_404(request, source, vuln_id)

    if request.POST.get("confirm", "").strip() != record.id:
        request.session.flash(
            f"Please confirm the vulnerability id {record.id!r} to delete.",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.vulnerabilities.detail", source=source, id=vuln_id
            )
        )

    request.db.delete(record)
    request.session.flash(
        f"Deleted vulnerability {source}:{vuln_id} and all release associations.",
        queue="success",
    )
    return HTTPSeeOther(request.route_path("admin.vulnerabilities.list"))


@view_config(
    route_name="admin.vulnerabilities.bulk_delete",
    permission=Permissions.AdminVulnerabilitiesWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def vulnerability_bulk_delete(request: Request) -> HTTPSeeOther:
    q: str = request.POST.get("q", "").strip()
    confirm: str = request.POST.get("confirm", "").strip()

    if not q:
        request.session.flash(
            "Provide a filter to bulk delete vulnerabilities.", queue="error"
        )
        return HTTPSeeOther(request.route_path("admin.vulnerabilities.list"))

    if confirm != q:
        request.session.flash(
            "Confirmation did not match the filter. No vulnerabilities were deleted.",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("admin.vulnerabilities.list", _query={"q": q})
        )

    predicate = _filter_predicate(q)

    # Guard against a runaway filter (e.g. bare `%`) cascade-deleting millions
    # of release associations.
    count: int = (
        request.db.scalar(
            select(func.count()).select_from(VulnerabilityRecord).where(predicate)
        )
        or 0
    )
    if count > BULK_DELETE_LIMIT:
        request.session.flash(
            f"Filter matches {count} records "
            f"(limit {BULK_DELETE_LIMIT}). Refine the filter.",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("admin.vulnerabilities.list", _query={"q": q})
        )

    # Core DELETE in a single statement; ON DELETE CASCADE on the FK handles
    # release_vulnerabilities cleanup at the Postgres level.
    request.db.execute(delete(VulnerabilityRecord).where(predicate))

    request.session.flash(
        f"Deleted {count} vulnerability record(s) matching {q!r}.",
        queue="success",
    )
    return HTTPSeeOther(request.route_path("admin.vulnerabilities.list"))
