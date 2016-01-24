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
from pyramid.response import FileIter, Response
from pyramid.view import view_config
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import Release, File, Role


@view_config(
    route_name="packaging.project",
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,                         # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def project_detail(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
        )

    try:
        release = (
            request.db.query(Release)
                      .options(joinedload(Release.uploader))
                      .filter(Release.project == project)
                      .order_by(Release._pypi_ordering.desc())
                      .limit(1)
                      .one()
        )
    except NoResultFound:
        return HTTPNotFound()

    return release_detail(release, request)


@view_config(
    route_name="packaging.release",
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,                         # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def release_detail(release, request):
    project = release.project

    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
        )

    # Get all of the registered versions for this Project, in order of newest
    # to oldest.
    all_releases = (
        request.db.query(Release)
                  .filter(Release.project == project)
                  .with_entities(Release.version, Release.created)
                  .order_by(Release._pypi_ordering.desc())
                  .all()
    )

    # Get all of the maintainers for this project.
    maintainers = [
        r.user
        for r in (
            request.db.query(Role)
            .join(User)
            .filter(Role.project == project)
            .distinct(User.username)
            .order_by(User.username)
            .all()
        )
    ]

    return {
        "project": project,
        "release": release,
        "files": release.files.all(),
        "all_releases": all_releases,
        "maintainers": maintainers,
    }


@view_config(
    route_name="packaging.file",
    decorator=[
        cache_control(365 * 24 * 60 * 60),            # 1 year
        origin_cache(
            365 * 24 * 60 * 60,                       # 1 year
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def packages(request):
    # The amount of logic that we can do in this view is very limited, this
    # view needs to be able to be handled by Fastly directly hitting S3 instead
    # of actually hitting this view. This more or less means that we're limited
    # to just serving the actual file.

    # Grab the path of the file that we're attempting to serve
    path = request.matchdict["path"]

    # We need to look up the File that is associated with this path, either the
    # package path or the pgp path. If that doesn't exist then we'll bail out
    # early with a 404.
    try:
        file_ = (
            request.db.query(File)
                      .options(joinedload(File.release)
                               .joinedload(Release.project))
                      .filter((File.path == path) | (File.pgp_path == path))
                      .one()
        )
    except NoResultFound:
        return HTTPNotFound()

    # If this request is for a PGP signature, and the file doesn't have a PGP
    # signature, then we can go ahead and 404 now before hitting the file
    # storage.
    if path == file_.pgp_path and not file_.has_signature:
        return HTTPNotFound()

    # Try to get the file from the file file storage service, logging an error
    # and returning a HTTPNotFound if one can't be found.
    try:
        f = request.find_service(IFileStorage).get(path)
    except FileNotFoundError:
        request.log.error("missing file data", path=path)
        return HTTPNotFound()

    # If the path we're accessing is the path for the package itself, as
    # opposed to the path for the signature, then we can include a
    # Content-Length header.
    content_length = None
    if path == file_.path:
        content_length = file_.size

    return Response(
        app_iter=FileIter(f),
        # We use application/octet-stream instead of something nicer because
        # different HTTP libraries will treat different combinations of
        # Content-Type and Content-Encoding differently. The only thing that
        # works sanely across all things without having something in the middle
        # decide it can decompress the result to "help" the end user is with
        # Content-Type: applicaton/octet-stream and no Content-Encoding.
        content_type="application/octet-stream",
        content_encoding=None,
        # We need to specify an ETag for this response. Since ETags compared
        # between URLs have no meaning (and thus, is safe for two URLs to share
        # the same ETag) we will just use the MD5 hash of the package as our
        # ETag.
        etag=file_.md5_digest,
        # Similarly to the ETag header, we'll just use the date that the file
        # was uploaded as the Last-Modified header.
        last_modified=file_.upload_time,
        # If we have a Content-Length, we'll go ahead and use it here to
        # hopefully enable the server and clients alike to be smarter about how
        # they handle downloading this response.
        content_length=content_length,
    )
