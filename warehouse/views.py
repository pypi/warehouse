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

from pyramid.httpexceptions import (
    HTTPSeeOther,
    HTTPMovedPermanently,
)
from pyramid.view import (
    forbidden_view_config,
    notfound_view_config,
    view_config,
)

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.packaging.models import Project, Release, File
from warehouse.accounts.models import User


# If a route matches with a slash appended to it, redirect to that route
# instead of returning a HTTPNotFound.
@notfound_view_config(
    append_slash=HTTPMovedPermanently,
    renderer='templates/404.html',
)
def notfound(context, request):
    return {}


@forbidden_view_config(renderer='templates/500.html')
def forbidden(exc, request):
    # If the forbidden error is because the user isn't logged in, then we'll
    # redirect them to the log in page.
    if request.authenticated_userid is None:
        url = request.route_url(
            "accounts.login",
            _query={REDIRECT_FIELD_NAME: request.path_qs},
        )
        return HTTPSeeOther(url)

    # If we've reached here, then the user is logged in and they are genuinely
    # not allowed to access this page.
    return {}


@view_config(
    route_name="index",
    renderer="index.html",
)
def index(request):
    latest_updated_releases = request.db.query(Release)\
                                        .order_by(Release.created.desc())[:20]
    num_projects = request.db.query(Project).count()
    num_users = request.db.query(User).count()
    num_files = request.db.query(File).count()
    num_releases = request.db.query(Release).count()

    return {
        'latest_updated_releases': latest_updated_releases,
        'num_projects': num_projects,
        'num_users': num_users,
        'num_releases': num_releases,
        'num_files': num_files,
    }
