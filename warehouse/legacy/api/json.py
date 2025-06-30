# SPDX-License-Identifier: Apache-2.0

from packaging.utils import canonicalize_name, canonicalize_version
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Load, contains_eager, joinedload

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import (
    Description,
    File,
    LifecycleStatus,
    Project,
    Release,
    ReleaseURL,
)
from warehouse.utils.cors import _CORS_HEADERS

_RELEASE_CACHE_DECORATOR = [
    cache_control(15 * 60),  # 15 minutes
    origin_cache(
        1 * 24 * 60 * 60,  # 1 day
        stale_while_revalidate=5 * 60,  # 5 minutes
        stale_if_error=1 * 24 * 60 * 60,  # 1 day
        keys=["all-legacy-json", "release-legacy-json"],
    ),
]

_PROJECT_CACHE_DECORATOR = [
    cache_control(15 * 60),  # 15 minutes
    origin_cache(
        1 * 24 * 60 * 60,  # 1 day
        stale_while_revalidate=5 * 60,  # 5 minutes
        stale_if_error=1 * 24 * 60 * 60,  # 1 day
        keys=["all-legacy-json", "project-legacy-json"],
    ),
]


def _json_data(request, project, release, *, all_releases):
    # Get all of the releases and files for this project.
    release_files = (
        request.db.query(Release, File)
        .options(
            Load(Release).load_only(
                Release.version,
                Release.requires_python,
                Release.yanked,
                Release.yanked_reason,
            )
        )
        .outerjoin(File)
        .filter(Release.project == project)
    )

    # If we're not looking for all_releases, then we'll filter this further
    # to just this release.
    if not all_releases:
        release_files = release_files.filter(Release.id == release.id)

    # Get the raw description and description content type for this release
    release_description = (
        request.db.query(Description)
        .options(Load(Description).load_only(Description.content_type, Description.raw))
        .filter(Description.release == release)
        .one()
    )

    # Finally set an ordering, and execute the query.
    release_files = release_files.order_by(
        Release._pypi_ordering.desc(), File.filename
    ).all()

    # Map our releases + files into a dictionary that maps each release to a
    # list of all its files.
    releases_and_files: dict[Release, list[File]] = {}
    for r, file_ in release_files:
        files = releases_and_files.setdefault(r, [])
        if file_ is not None:
            files.append(file_)

    # Serialize our database objects to match the way that PyPI legacy
    # presented this data.
    releases = {
        r.version: [
            {
                "filename": f.filename,
                "packagetype": f.packagetype,
                "python_version": f.python_version,
                # TODO: Remove this once we've had a long enough time with it
                #       here to consider it no longer in use.
                "has_sig": False,
                "comment_text": f.comment_text,
                "md5_digest": f.md5_digest,
                "digests": {
                    "md5": f.md5_digest,
                    "sha256": f.sha256_digest,
                    "blake2b_256": f.blake2_256_digest,
                },
                "size": f.size,
                # TODO: Remove this once we've had a long enough time with it
                #       here to consider it no longer in use.
                "downloads": -1,
                "upload_time": f.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "upload_time_iso_8601": f.upload_time.isoformat() + "Z",
                "url": request.route_url("packaging.file", path=f.path),
                "requires_python": r.requires_python if r.requires_python else None,
                "yanked": r.yanked,
                "yanked_reason": r.yanked_reason or None,
            }
            for f in fs
        ]
        for r, fs in releases_and_files.items()
    }

    # Serialize a list of vulnerabilities for this release
    vulnerabilities = [
        {
            "id": vulnerability_record.id,
            "source": vulnerability_record.source,
            "link": vulnerability_record.link,
            "aliases": vulnerability_record.aliases,
            "details": vulnerability_record.details,
            "summary": vulnerability_record.summary,
            "fixed_in": vulnerability_record.fixed_in,
            "withdrawn": (
                vulnerability_record.withdrawn.strftime("%Y-%m-%dT%H:%M:%SZ")
                if vulnerability_record.withdrawn
                else None
            ),
        }
        for vulnerability_record in release.vulnerabilities
    ]

    data = {
        "info": {
            "name": project.name,
            "version": release.version,
            "summary": release.summary,
            "description_content_type": release_description.content_type,
            "description": release_description.raw,
            "keywords": release.keywords,
            "license": release.license,
            "license_expression": release.license_expression,
            "license_files": release.license_files,
            "classifiers": list(release.classifiers),
            "author": release.author,
            "author_email": release.author_email,
            "maintainer": release.maintainer,
            "maintainer_email": release.maintainer_email,
            "requires_python": release.requires_python,
            "platform": release.platform,
            "downloads": {"last_day": -1, "last_week": -1, "last_month": -1},
            "package_url": request.route_url("packaging.project", name=project.name),
            "project_url": request.route_url("packaging.project", name=project.name),
            "project_urls": release.urls if release.urls else None,
            "release_url": request.route_url(
                "packaging.release", name=project.name, version=release.version
            ),
            "requires_dist": (
                list(release.requires_dist) if release.requires_dist else None
            ),
            "provides_extra": (
                list(release.provides_extra) if release.provides_extra else None
            ),
            "docs_url": project.documentation_url,
            "bugtrack_url": None,
            "home_page": release.home_page,
            "download_url": release.download_url,
            "yanked": release.yanked,
            "yanked_reason": release.yanked_reason or None,
            "dynamic": list(release.dynamic) if release.dynamic else None,
        },
        "urls": releases[release.version],
        "vulnerabilities": vulnerabilities,
        "last_serial": project.last_serial,
    }

    if all_releases:
        data["releases"] = releases

    return data


def latest_release_factory(request):
    normalized_name = canonicalize_name(request.matchdict["name"])

    try:
        latest = (
            request.db.query(Release.id, Release.version)
            .join(Release.project)
            .filter(Project.normalized_name == normalized_name)
            # Exclude projects in quarantine.
            .filter(
                Project.lifecycle_status.is_distinct_from(
                    LifecycleStatus.QuarantineEnter
                )
            )
            .order_by(
                Release.yanked.asc(),
                Release.is_prerelease.nullslast(),
                Release._pypi_ordering.desc(),
            )
            .limit(1)
            .one()
        )
    except NoResultFound:
        return HTTPNotFound(headers=_CORS_HEADERS)

    release = (
        request.db.query(Release)
        .join(Project)
        .outerjoin(ReleaseURL)
        .options(
            contains_eager(Release.project),
            contains_eager(Release._project_urls),
            joinedload(Release._requires_dist),
        )
        .filter(Release.id == latest.id)
        .one()
    )

    return release


@view_config(
    route_name="legacy.api.json.project",
    context=Release,
    renderer="json",
    decorator=_PROJECT_CACHE_DECORATOR,
)
def json_project(release, request):
    project = release.project

    if project.normalized_name != request.matchdict["name"]:
        return HTTPMovedPermanently(
            request.current_route_path(name=project.normalized_name),
            headers=_CORS_HEADERS,
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Build our json data, including all releases because this is the root url
    # and changing this breaks bandersnatch
    # TODO: Eventually it would be nice to drop all_releases.
    return _json_data(request, project, release, all_releases=True)


@view_config(
    route_name="legacy.api.json.project_slash",
    context=Release,
    renderer="json",
    decorator=_PROJECT_CACHE_DECORATOR,
)
def json_project_slash(release, request):
    return json_project(release, request)


def release_factory(request):
    normalized_name = canonicalize_name(request.matchdict["name"])
    version = request.matchdict["version"]
    canonical_version = canonicalize_version(version)

    project_q = (
        request.db.query(Release)
        .join(Project)
        .outerjoin(ReleaseURL)
        .options(
            contains_eager(Release.project),
            contains_eager(Release._project_urls),
            joinedload(Release._requires_dist),
        )
        .filter(Project.normalized_name == normalized_name)
        # Exclude projects in quarantine.
        .filter(
            Project.lifecycle_status.is_distinct_from(LifecycleStatus.QuarantineEnter)
        )
    )

    try:
        release = project_q.filter(Release.canonical_version == canonical_version).one()
    except MultipleResultsFound:
        # There are multiple releases of this project which have the same
        # canonical version that were uploaded before we checked for
        # canonical version equivalence, so return the exact match instead
        try:
            release = project_q.filter(Release.version == version).one()
        except NoResultFound:
            # There are multiple releases of this project which have the
            # same canonical version, but none that have the exact version
            # specified, so just 404
            return HTTPNotFound(headers=_CORS_HEADERS)
    except NoResultFound:
        return HTTPNotFound(headers=_CORS_HEADERS)

    return release


@view_config(
    route_name="legacy.api.json.release",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
)
def json_release(release, request):
    project = release.project

    if project.normalized_name != request.matchdict["name"]:
        return HTTPMovedPermanently(
            request.current_route_path(name=project.normalized_name),
            headers=_CORS_HEADERS,
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Build our json data, with only this releases because this is a versioned url
    return _json_data(request, project, release, all_releases=False)


@view_config(
    route_name="legacy.api.json.release_slash",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
)
def json_release_slash(release, request):
    return json_release(release, request)
