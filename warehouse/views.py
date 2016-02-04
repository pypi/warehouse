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
from sqlalchemy.orm import aliased, joinedload

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.cache.http import cache_control
from warehouse.csrf import csrf_exempt
from warehouse.packaging.models import Project, Release, File
from warehouse.sessions import uses_session
from warehouse.utils.row_counter import RowCount
from warehouse.utils.paginate import ElasticsearchPage, paginate_url_factory


@view_config(context=HTTPException, decorator=[csrf_exempt])
@notfound_view_config(
    append_slash=HTTPMovedPermanently,
    decorator=[csrf_exempt],
)
def httpexception_view(exc, request):
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
    route_name="robots.txt",
    renderer="robots.txt",
    decorator=[
        cache_control(1 * 24 * 60 * 60),         # 1 day
        origin_cache(
            1 * 24 * 60 * 60,                    # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,     # 1 day
        ),
    ],
)
def robotstxt(request):
    request.response.content_type = "text/plain"
    return {}


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
    project_names = [
        r[0] for r in (
            request.db.query(File.name)
                   .group_by(File.name)
                   .order_by(func.sum(File.downloads).desc())
                   .limit(5)
                   .all())
    ]
    release_a = aliased(
        Release,
        request.db.query(Release)
                  .distinct(Release.name)
                  .filter(Release.name.in_(project_names))
                  .order_by(Release.name, Release._pypi_ordering.desc())
                  .subquery(),
    )
    top_projects = (
        request.db.query(release_a)
               .options(joinedload(release_a.project),
                        joinedload(release_a.uploader))
               .order_by(func.array_idx(project_names, release_a.name))
               .all()
    )

    latest_releases = (
        request.db.query(Release)
                  .options(joinedload(Release.project),
                           joinedload(Release.uploader))
                  .order_by(Release.created.desc())
                  .limit(5)
                  .all()
    )

    counts = dict(
        request.db.query(RowCount.table_name, RowCount.count)
                  .filter(
                      RowCount.table_name.in_([
                          Project.__tablename__,
                          Release.__tablename__,
                          File.__tablename__,
                          User.__tablename__,
                      ]))
                  .all()
    )

    return {
        "latest_releases": latest_releases,
        "top_projects": top_projects,
        "num_projects": counts.get(Project.__tablename__, 0),
        "num_releases": counts.get(Release.__tablename__, 0),
        "num_files": counts.get(File.__tablename__, 0),
        "num_users": counts.get(User.__tablename__, 0),
    }


@view_config(
    route_name="search",
    renderer="search/results.html",
    decorator=[
        origin_cache(
            1 * 60 * 60,                      # 1 hour
            stale_while_revalidate=10 * 60,   # 10 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects"],
        )
    ],
)
def search(request):
    if request.params.get("q"):
        query = request.es.query(
            "multi_match",
            query=request.params["q"],
            fields=[
                "name", "version", "author", "author_email", "maintainer",
                "maintainer_email", "home_page", "license", "summary",
                "description", "keywords", "platform", "download_url",
            ],
        ).suggest(
            name="name_suggestion",
            text=request.params["q"],
            term={"field": "name"}
        )
    else:
        query = request.es.query()

    page = ElasticsearchPage(
        query,
        page=int(request.params.get("page", 1)),
        url_maker=paginate_url_factory(request),
    )

    return {"page": page, "term": request.params.get("q")}


@view_config(
    route_name="includes.current-user-indicator",
    renderer="includes/current-user-indicator.html",
    decorator=[uses_session],
)
def current_user_indicator(request):
    return {}
