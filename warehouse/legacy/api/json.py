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

from packaging.utils import canonicalize_name, canonicalize_version
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm import Load, contains_eager, joinedload
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File, Project, Release, ReleaseURL

# Generate appropriate CORS headers for the JSON endpoint.
# We want to allow Cross-Origin requests here so that users can interact
# with these endpoints via XHR/Fetch APIs in the browser.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": ", ".join(
        [
            "Content-Type",
            "If-Match",
            "If-Modified-Since",
            "If-None-Match",
            "If-Unmodified-Since",
        ]
    ),
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Max-Age": "86400",  # 1 day.
    "Access-Control-Expose-Headers": ", ".join(["X-PyPI-Last-Serial"]),
}

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
                "version", "requires_python", "yanked", "yanked_reason"
            )
        )
        .outerjoin(File)
        .filter(Release.project == project)
    )

    # If we're not looking for all_releases, then we'll filter this further
    # to just this release.
    if not all_releases:
        release_files = release_files.filter(Release.id == release.id)

    # Finally set an ordering, and execute the query.
    release_files = release_files.order_by(
        Release._pypi_ordering.desc(), File.filename
    ).all()

    # Map our releases + files into a dictionary that maps each release to a
    # list of all its files.
    releases = {}
    for r, file_ in release_files:
        files = releases.setdefault(r, [])
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
                "has_sig": f.has_signature,
                "comment_text": f.comment_text,
                "md5_digest": f.md5_digest,
                "digests": {"md5": f.md5_digest, "sha256": f.sha256_digest},
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
        for r, fs in releases.items()
    }

    # Serialize a list of vulnerabilties for this release
    vulnerabilities = [
        {
            "id": vulnerability_record.id,
            "source": vulnerability_record.source,
            "link": vulnerability_record.link,
            "aliases": vulnerability_record.aliases,
            "details": vulnerability_record.details,
            "summary": vulnerability_record.summary,
            "fixed_in": vulnerability_record.fixed_in,
        }
        for vulnerability_record in release.vulnerabilities
    ]

    data = {
        "info": {
            "name": project.name,
            "version": release.version,
            "summary": release.summary,
            "description_content_type": release.description.content_type,
            "description": release.description.raw,
            "keywords": release.keywords,
            "license": release.license,
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
            "docs_url": project.documentation_url,
            "bugtrack_url": None,
            "home_page": release.home_page,
            "download_url": release.download_url,
            "yanked": release.yanked,
            "yanked_reason": release.yanked_reason or None,
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
