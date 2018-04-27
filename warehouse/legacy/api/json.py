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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm import Load
from sqlalchemy.orm.exc import NoResultFound

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File, Release, Project


# Generate appropriate CORS headers for the JSON endpoint.
# We want to allow Cross-Origin requests here so that users can interact
# with these endpoints via XHR/Fetch APIs in the browser.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": ", ".join([
        "Content-Type",
        "If-Match",
        "If-Modified-Since",
        "If-None-Match",
        "If-Unmodified-Since",
    ]),
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Max-Age": "86400",  # 1 day.
    "Access-Control-Expose-Headers": ", ".join([
        "X-PyPI-Last-Serial",
    ]),
}


@view_config(
    route_name="legacy.api.json.project",
    context=Project,
    renderer="json",
    decorator=[
        cache_control(15 * 60),               # 15 minutes
        origin_cache(
            1 * 24 * 60 * 60,                 # 1 day
            stale_while_revalidate=5 * 60,    # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def json_project(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
            headers=_CORS_HEADERS
        )

    try:
        release = (
            request.db.query(Release)
                      .filter(Release.project == project)
                      .order_by(
                          Release.is_prerelease.nullslast(),
                          Release._pypi_ordering.desc())
                      .limit(1)
                      .one()
        )
    except NoResultFound:
        return HTTPNotFound(headers=_CORS_HEADERS)

    return json_release(release, request)


@view_config(
    route_name="legacy.api.json.release",
    context=Release,
    renderer="json",
    decorator=[
        cache_control(15 * 60),               # 15 minutes
        origin_cache(
            1 * 24 * 60 * 60,                 # 1 day
            stale_while_revalidate=5 * 60,    # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def json_release(release, request):
    project = release.project

    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
            headers=_CORS_HEADERS
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Get all of the releases and files for this project.
    release_files = (
        request.db.query(Release, File)
               .options(Load(Release).load_only('version'))
               .outerjoin(File)
               .filter(Release.project == project)
               .order_by(Release._pypi_ordering.desc(), File.filename)
               .all()
    )

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
                "digests": {
                    "md5": f.md5_digest,
                    "sha256": f.sha256_digest,
                },
                "size": f.size,
                # TODO: Remove this once we've had a long enough time with it
                #       here to consider it no longer in use.
                "downloads": -1,
                "upload_time": f.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "url": request.route_url("packaging.file", path=f.path),
            }
            for f in fs
        ]
        for r, fs in releases.items()
    }

    return {
        "info": {
            "name": project.name,
            "version": release.version,
            "summary": release.summary,
            "description_content_type": release.description_content_type,
            "description": release.description,
            "keywords": release.keywords,
            "license": release.license,
            "classifiers": list(release.classifiers),
            "author": release.author,
            "author_email": release.author_email,
            "maintainer": release.maintainer,
            "maintainer_email": release.maintainer_email,
            "requires_python": release.requires_python,
            "platform": release.platform,
            "downloads": {
                "last_day": -1,
                "last_week": -1,
                "last_month": -1,
            },
            "package_url": request.route_url(
                "packaging.project",
                name=project.name,
            ),
            "project_url": request.route_url(
                "packaging.project",
                name=project.name,
            ),
            "release_url": request.route_url(
                "packaging.release",
                name=project.name,
                version=release.version,
            ),
            "requires_dist": (list(release.requires_dist)
                              if release.requires_dist else None),
            "docs_url": project.documentation_url,
            "bugtrack_url": project.bugtrack_url,
            "home_page": release.home_page,
            "download_url": release.download_url,
        },
        "urls": releases[release.version],
        "releases": releases,
        "last_serial": project.last_serial,
    }
