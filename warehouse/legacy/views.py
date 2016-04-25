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

from pyramid.httpexceptions import HTTPTemporaryRedirect, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File


@view_config(
    route_name="legacy.file.redirect",
    decorator=[
        origin_cache(
            365 * 24 * 60 * 60,                       # 1 year
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def file_redirect(request):
    # Pull the information we need to find this file out of the URL.
    pyversion, first, name, filename = request.matchdict["path"].split("/")

    # This is just a simple sanity check so that we don't have to look this up
    # in the database since it would otherwise be redundant.
    if first != name[0]:
        return HTTPNotFound()

    # If the filename we're looking for is a signature, then we'll need to turn
    # this into the *real* filename and a note that we're looking for the
    # signature.
    if filename.endswith(".asc"):
        filename = filename[:-4]
        signature = True
    else:
        signature = False

    # Look up to see if there is a file that match this python version, name,
    # and filename in the database. If there isn't we'll 404 here.
    try:
        file_ = (
            request.db.query(File)
                      .filter((File.python_version == pyversion) &
                              (File.name == name) &
                              (File.filename == filename))
                      .one()
        )
    except NoResultFound:
        return HTTPNotFound()

    # If we've located the file, but we're actually looking for the signature
    # then we'll check to see if this file object has a signature associated
    # with it. If it does we'll redirect to that, if not then we'll return a
    # 404.
    if signature:
        if file_.has_signature:
            return HTTPTemporaryRedirect(
                request.route_path("packaging.file", path=file_.pgp_path)
            )
        else:
            return HTTPNotFound()

    # Finally if we've gotten here, then we want to just return a redirect to
    # the actual file.
    return HTTPTemporaryRedirect(
        request.route_path("packaging.file", path=file_.path)
    )
