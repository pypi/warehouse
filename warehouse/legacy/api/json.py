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

from collections import OrderedDict

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm import Load
from sqlalchemy.orm.exc import NoResultFound

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage.forms import CreateMacaroonForm
from warehouse.packaging.models import File, Project, Release

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

_CACHE_DECORATOR = [
    cache_control(15 * 60),  # 15 minutes
    origin_cache(
        1 * 24 * 60 * 60,  # 1 day
        stale_while_revalidate=5 * 60,  # 5 minutes
        stale_if_error=1 * 24 * 60 * 60,  # 1 day
    ),
]


@view_config(
    route_name="legacy.api.json.project",
    context=Project,
    renderer="json",
    decorator=_CACHE_DECORATOR,
)
def json_project(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name), headers=_CORS_HEADERS
        )

    try:
        release = (
            request.db.query(Release)
            .filter(Release.project == project)
            .order_by(Release.is_prerelease.nullslast(), Release._pypi_ordering.desc())
            .limit(1)
            .one()
        )
    except NoResultFound:
        return HTTPNotFound(headers=_CORS_HEADERS)

    return json_release(release, request)


@view_config(
    route_name="legacy.api.json.project_slash",
    context=Project,
    decorator=_CACHE_DECORATOR,
)
def json_project_slash(project, request):
    return HTTPMovedPermanently(
        # Respond with redirect to url without trailing slash
        request.route_path("legacy.api.json.project", name=project.name),
        headers=_CORS_HEADERS,
    )


@view_config(
    route_name="legacy.api.json.release",
    context=Release,
    renderer="json",
    decorator=_CACHE_DECORATOR,
)
def json_release(release, request):
    project = release.project

    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name), headers=_CORS_HEADERS
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Get all of the releases and files for this project.
    release_files = (
        request.db.query(Release, File)
        .options(Load(Release).load_only("version", "requires_python"))
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
                "digests": {"md5": f.md5_digest, "sha256": f.sha256_digest},
                "size": f.size,
                # TODO: Remove this once we've had a long enough time with it
                #       here to consider it no longer in use.
                "downloads": -1,
                "upload_time": f.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "upload_time_iso_8601": f.upload_time.isoformat() + "Z",
                "url": request.route_url("packaging.file", path=f.path),
                "requires_python": r.requires_python if r.requires_python else None,
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
            "project_urls": OrderedDict(release.urls) if release.urls else None,
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
        },
        "urls": releases[release.version],
        "releases": releases,
        "last_serial": project.last_serial,
    }


@view_config(
    route_name="legacy.api.json.release_slash",
    context=Release,
    decorator=_CACHE_DECORATOR,
)
def json_release_slash(release, request):
    return HTTPMovedPermanently(
        # Respond with redirect to url without trailing slash
        request.route_path(
            "legacy.api.json.release",
            name=release.project.name,
            version=release.version,
        ),
        headers=_CORS_HEADERS,
    )


@view_config(
    route_name="legacy.api.json.token.new",
    renderer="json",
    require_methods=["POST"],
    uses_session=True,
    permission="manage:user",
    require_csrf=False,
)
def create_token(request):
    def _fail(message):
        request.response.status_code = 400
        return {"success": False, "message": message}

    if request.authenticated_userid is None:
        return _fail("invalid authentication token")

    # Sanity-check our JSON payload. Ideally this would be done in a form,
    # but WTForms isn't well equipped to handle JSON bodies.
    try:
        payload = request.json_body
        if not isinstance(payload, dict):
            raise ValueError
    except Exception:
        return _fail("invalid payload")

    macaroon_service = request.find_service(IMacaroonService, context=None)

    form = CreateMacaroonForm(
        **payload,
        user_id=request.user.id,
        macaroon_service=macaroon_service,
        all_projects=request.user.projects,
    )
    if not form.validate():
        errors = "\n".join(
            [str(error) for error_list in form.errors.values() for error in error_list]
        )
        return _fail(errors)

    serialized_macaroon, _ = macaroon_service.create_macaroon(
        location=request.domain,
        user_id=request.user.id,
        description=form.description.data,
        caveats=form.validated_caveats,
    )
    request.user.record_event(
        tag="account:api_token:added",
        ip_address=request.remote_addr,
        additional={
            "description": form.description.data,
            "caveats": form.validated_caveats,
        },
    )

    permissions = form.validated_caveats["permissions"]
    if "projects" in permissions:
        project_names = [project["name"] for project in permissions["projects"]]
        projects = [
            project
            for project in request.user.projects
            if project.normalized_name in project_names
        ]
        for project in projects:
            # NOTE: We don't disclose the full caveats for this token
            # to the project event log, since the token could also
            # have access to projects that this project's owner
            # isn't aware of.
            project.record_event(
                tag="project:api_token:added",
                ip_address=request.remote_addr,
                additional={
                    "description": form.description.data,
                    "user": request.user.username,
                },
            )

    return {"success": True, "token": serialized_macaroon}
