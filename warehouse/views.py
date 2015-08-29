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
    HTTPException, HTTPSeeOther, HTTPMovedPermanently,
)
from pyramid.view import (
    notfound_view_config, forbidden_view_config, view_config,
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.csrf import csrf_exempt
from warehouse.packaging.models import Project, Release, File
from warehouse.sessions import uses_session


@view_config(context=HTTPException, decorator=[csrf_exempt])
@notfound_view_config(
    append_slash=HTTPMovedPermanently,
    decorator=[csrf_exempt],
)
def exception_view(exc, request):
    return exc


@forbidden_view_config()
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
    # TODO: Style the forbidden page.
    return exc


@view_config(
    route_name="index",
    renderer="index.html",
    decorator=[
        origin_cache(
            1 * 60 * 60,                      # 1 hour
            stale_while_revalidate=10 * 60,   # 10 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects"],
        ),
    ]
)
def index(request):
    latest_updated_releases = (
        request.db.query(Release)
                  .options(joinedload(Release.project))
                  .order_by(Release.created.desc())
                  .limit(20)
                  .all()
    )
    num_projects = request.db.query(func.count(Project.name)).scalar()
    num_users = request.db.query(func.count(User.id)).scalar()
    num_files = request.db.query(func.count(File.id)).scalar()
    num_releases = request.db.query(func.count(Release.name)).scalar()

    return {
        'latest_updated_releases': latest_updated_releases,
        'num_projects': num_projects,
        'num_users': num_users,
        'num_releases': num_releases,
        'num_files': num_files,
    }


@view_config(
    route_name="esi.current-user-indicator",
    renderer="includes/current-user-indicator.html",
    decorator=[uses_session],
)
def current_user_indicator(request):
    return {}
