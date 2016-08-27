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

import collections

from pyramid.httpexceptions import (
    HTTPException, HTTPSeeOther, HTTPMovedPermanently, HTTPNotFound,
    HTTPBadRequest,
)
from pyramid.view import (
    notfound_view_config, forbidden_view_config, view_config,
)
from elasticsearch_dsl import Q
from sqlalchemy import func
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import exists

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.cache.http import cache_control
from warehouse.classifiers.models import Classifier
from warehouse.packaging.models import (
    Project, Release, File, release_classifiers,
)
from warehouse.utils.row_counter import RowCount
from warehouse.utils.paginate import ElasticsearchPage, paginate_url_factory


SEARCH_FIELDS = [
    "author", "author_email", "description", "download_url", "home_page",
    "keywords", "license", "maintainer", "maintainer_email", "normalized_name",
    "platform", "summary",
]
SEARCH_BOOSTS = {
    "normalized_name": 10,
    "description": 5,
    "keywords": 5,
    "summary": 5,
}
SEARCH_FILTER_ORDER = (
    "Programming Language",
    "License",
    "Framework",
    "Topic",
    "Intended Audience",
    "Environment",
    "Operating System",
    "Natural Language",
    "Development Status",
)


@view_config(context=HTTPException)
@notfound_view_config(append_slash=HTTPMovedPermanently)
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
    route_name="opensearch.xml",
    renderer="opensearch.xml",
    decorator=[
        cache_control(1 * 24 * 60 * 60),         # 1 day
        origin_cache(
            1 * 24 * 60 * 60,                    # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,     # 1 day
        )
    ]
)
def opensearchxml(request):
    request.response.content_type = "text/xml"
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
               .options(joinedload(release_a.project))
               .order_by(func.array_idx(project_names, release_a.name))
               .all()
    )

    latest_releases = (
        request.db.query(Release)
                  .options(joinedload(Release.project))
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

    q = request.params.get("q", '')

    if q:
        should = []
        for field in SEARCH_FIELDS:
            kw = {"query": q}
            if field in SEARCH_BOOSTS:
                kw["boost"] = SEARCH_BOOSTS[field]
            should.append(Q("match", **{field: kw}))

        # Add a prefix query if ``q`` is longer than one character.
        if len(q) > 1:
            should.append(Q('prefix', normalized_name=q))

        query = request.es.query("dis_max", queries=should)
        query = query.suggest("name_suggestion", q, term={"field": "name"})
    else:
        query = request.es.query()

    if request.params.get("o"):
        query = query.sort(request.params["o"])

    if request.params.getall("c"):
        query = query.filter("terms", classifiers=request.params.getall("c"))

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    page = ElasticsearchPage(
        query,
        page=page_num,
        url_maker=paginate_url_factory(request),
    )

    if page.page_count and page_num > page.page_count:
        return HTTPNotFound()

    available_filters = collections.defaultdict(list)

    classifiers_q = (
        request.db.query(Classifier)
        .with_entities(Classifier.classifier)
        .filter(
            exists([release_classifiers.c.trove_id])
            .where(release_classifiers.c.trove_id == Classifier.id)
        )
        .order_by(Classifier.classifier)
    )

    for cls in classifiers_q:
        first, *_ = cls.classifier.split(' :: ')
        available_filters[first].append(cls.classifier)

    def filter_key(item):
        try:
            return 0, SEARCH_FILTER_ORDER.index(item[0]), item[0]
        except ValueError:
            return 1, 0, item[0]

    return {
        "page": page,
        "term": q,
        "order": request.params.get("o", ''),
        "available_filters": sorted(available_filters.items(), key=filter_key),
        "applied_filters": request.params.getall("c"),
    }


@view_config(
    route_name="includes.current-user-indicator",
    renderer="includes/current-user-indicator.html",
    uses_session=True,
)
def current_user_indicator(request):
    return {}


@view_config(route_name="health", renderer="string")
def health(request):
    # This will ensure that we can access the database and run queries against
    # it without doing anything that will take a lock or block other queries.
    request.db.execute("SELECT 1")

    # Nothing will actually check this, but it's a little nicer to have
    # something to return besides an empty body.
    return "OK"
