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
import re

import elasticsearch

from pyramid.httpexceptions import (
    HTTPException,
    HTTPSeeOther,
    HTTPMovedPermanently,
    HTTPNotFound,
    HTTPBadRequest,
    HTTPServiceUnavailable,
    exception_response,
)
from pyramid.exceptions import PredicateMismatch
from pyramid.renderers import render_to_response
from pyramid.response import Response
from pyramid.view import (
    notfound_view_config,
    forbidden_view_config,
    exception_view_config,
    view_config,
)
from elasticsearch_dsl import Q
from sqlalchemy import func
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import exists

from warehouse.db import DatabaseNotAvailable
from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.cache.http import add_vary, cache_control
from warehouse.classifiers.models import Classifier
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import Project, Release, File, release_classifiers
from warehouse.search.queries import SEARCH_BOOSTS, SEARCH_FIELDS, SEARCH_FILTER_ORDER
from warehouse.utils.row_counter import RowCount
from warehouse.utils.paginate import ElasticsearchPage, paginate_url_factory


# 403, 404, 410, 500,


@view_config(context=HTTPException)
@notfound_view_config(append_slash=HTTPMovedPermanently)
def httpexception_view(exc, request):
    # This special case exists for the easter egg that appears on the 404
    # response page. We don't generally allow youtube embeds, but we make an
    # except for this one.
    if isinstance(exc, HTTPNotFound):
        request.find_service(name="csp").merge(
            {
                "frame-src": ["https://www.youtube-nocookie.com"],
                "script-src": ["https://www.youtube.com", "https://s.ytimg.com"],
            }
        )
    try:
        # Lightweight version of 404 page for `/simple/`
        if isinstance(exc, HTTPNotFound) and request.path.startswith("/simple/"):
            response = Response(body="404 Not Found", content_type="text/plain")
        else:
            response = render_to_response(
                "{}.html".format(exc.status_code), {}, request=request
            )
    except LookupError:
        # We don't have a customized template for this error, so we'll just let
        # the default happen instead.
        return exc

    # Copy over the important values from our HTTPException to our new response
    # object.
    response.status = exc.status
    response.headers.extend(
        (k, v) for k, v in exc.headers.items() if k not in response.headers
    )

    return response


@forbidden_view_config()
@exception_view_config(PredicateMismatch)
def forbidden(exc, request, redirect_to="accounts.login"):
    # If the forbidden error is because the user isn't logged in, then we'll
    # redirect them to the log in page.
    if request.authenticated_userid is None:
        url = request.route_url(
            redirect_to, _query={REDIRECT_FIELD_NAME: request.path_qs}
        )
        return HTTPSeeOther(url)

    # If we've reached here, then the user is logged in and they are genuinely
    # not allowed to access this page.
    return httpexception_view(exc, request)


@forbidden_view_config(path_info=r"^/_includes/")
@exception_view_config(PredicateMismatch, path_info=r"^/_includes/")
def forbidden_include(exc, request):
    # If the forbidden error is for a client-side-include, just return an empty
    # response instead of redirecting
    return Response(status=403)


@view_config(context=DatabaseNotAvailable)
def service_unavailable(exc, request):
    return httpexception_view(HTTPServiceUnavailable(), request)


@view_config(
    route_name="robots.txt",
    renderer="robots.txt",
    decorator=[
        cache_control(1 * 24 * 60 * 60),  # 1 day
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
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
        cache_control(1 * 24 * 60 * 60),  # 1 day
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def opensearchxml(request):
    request.response.content_type = "text/xml"
    return {}


@view_config(
    route_name="index",
    renderer="index.html",
    decorator=[
        origin_cache(
            1 * 60 * 60,  # 1 hour
            stale_while_revalidate=10 * 60,  # 10 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects", "trending"],
        )
    ],
)
def index(request):
    project_names = [
        r[0]
        for r in (
            request.db.query(Project.name)
            .order_by(Project.zscore.desc().nullslast(), func.random())
            .limit(5)
            .all()
        )
    ]
    release_a = aliased(
        Release,
        request.db.query(Release)
        .distinct(Release.name)
        .filter(Release.name.in_(project_names))
        .order_by(
            Release.name,
            Release.is_prerelease.nullslast(),
            Release._pypi_ordering.desc(),
        )
        .subquery(),
    )
    trending_projects = (
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
            RowCount.table_name.in_(
                [
                    Project.__tablename__,
                    Release.__tablename__,
                    File.__tablename__,
                    User.__tablename__,
                ]
            )
        )
        .all()
    )

    return {
        "latest_releases": latest_releases,
        "trending_projects": trending_projects,
        "num_projects": counts.get(Project.__tablename__, 0),
        "num_releases": counts.get(Release.__tablename__, 0),
        "num_files": counts.get(File.__tablename__, 0),
        "num_users": counts.get(User.__tablename__, 0),
    }


@view_config(route_name="classifiers", renderer="pages/classifiers.html")
def classifiers(request):
    classifiers = (
        request.db.query(Classifier.classifier)
        .filter(Classifier.deprecated.is_(False))
        .order_by(Classifier.classifier)
        .all()
    )

    return {"classifiers": classifiers}


@view_config(
    route_name="search",
    renderer="search/results.html",
    decorator=[
        origin_cache(
            1 * 60 * 60,  # 1 hour
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects"],
        )
    ],
)
def search(request):
    metrics = request.find_service(IMetricsService, context=None)

    q = request.params.get("q", "")
    q = q.replace("'", '"')

    if q:
        bool_query = gather_es_queries(q)

        query = request.es.query(bool_query)

        query = query.suggest("name_suggestion", q, term={"field": "name"})
    else:
        query = request.es.query()

    if request.params.get("o"):
        sort_key = request.params["o"]
        if sort_key.startswith("-"):
            sort = {sort_key[1:]: {"order": "desc", "unmapped_type": "long"}}
        else:
            sort = {sort_key: {"unmapped_type": "long"}}

        query = query.sort(sort)

    # Require match to all specified classifiers
    for classifier in request.params.getall("c"):
        query = query.filter("terms", classifiers=[classifier])

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    try:
        page = ElasticsearchPage(
            query, page=page_num, url_maker=paginate_url_factory(request)
        )
    except elasticsearch.TransportError:
        metrics.increment("warehouse.views.search.error")
        raise HTTPServiceUnavailable

    if page.page_count and page_num > page.page_count:
        raise HTTPNotFound

    available_filters = collections.defaultdict(list)

    classifiers_q = (
        request.db.query(Classifier)
        .with_entities(Classifier.classifier)
        .filter(Classifier.deprecated.is_(False))
        .filter(
            exists([release_classifiers.c.trove_id]).where(
                release_classifiers.c.trove_id == Classifier.id
            )
        )
        .order_by(Classifier.classifier)
    )

    for cls in classifiers_q:
        first, *_ = cls.classifier.split(" :: ")
        available_filters[first].append(cls.classifier)

    def filter_key(item):
        try:
            return 0, SEARCH_FILTER_ORDER.index(item[0]), item[0]
        except ValueError:
            return 1, 0, item[0]

    metrics = request.find_service(IMetricsService, context=None)
    metrics.histogram("warehouse.views.search.results", page.item_count)

    return {
        "page": page,
        "term": q,
        "order": request.params.get("o", ""),
        "available_filters": sorted(available_filters.items(), key=filter_key),
        "applied_filters": request.params.getall("c"),
    }


@view_config(
    route_name="stats",
    renderer="pages/stats.html",
    decorator=[
        add_vary("Accept"),
        cache_control(1 * 24 * 60 * 60),  # 1 day
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
@view_config(
    route_name="stats.json",
    renderer="json",
    decorator=[
        add_vary("Accept"),
        cache_control(1 * 24 * 60 * 60),  # 1 day
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
    accept="application/json",
)
def stats(request):
    total_size_query = request.db.query(func.sum(File.size)).all()
    top_100_packages = (
        request.db.query(File.name, func.sum(File.size))
        .group_by(File.name)
        .order_by(func.sum(File.size).desc())
        .limit(100)
        .all()
    )
    # Move top packages into a dict to make JSON more self describing
    top_packages = {
        pkg_name: {"size": pkg_bytes} for pkg_name, pkg_bytes in top_100_packages
    }

    return {"total_packages_size": total_size_query[0][0], "top_packages": top_packages}


@view_config(
    route_name="includes.current-user-indicator",
    renderer="includes/current-user-indicator.html",
    uses_session=True,
)
def current_user_indicator(request):
    return {}


@view_config(
    route_name="includes.flash-messages",
    renderer="includes/flash-messages.html",
    uses_session=True,
)
def flash_messages(request):
    return {}


@view_config(route_name="health", renderer="string")
def health(request):
    # This will ensure that we can access the database and run queries against
    # it without doing anything that will take a lock or block other queries.
    request.db.execute("SELECT 1")

    # Nothing will actually check this, but it's a little nicer to have
    # something to return besides an empty body.
    return "OK"


@view_config(route_name="force-status")
def force_status(request):
    try:
        raise exception_response(int(request.matchdict["status"]))
    except KeyError:
        raise exception_response(404) from None


def filter_query(s):
    """
    Filters given query with the below regex
    and returns lists of quoted and unquoted strings
    """
    matches = re.findall(r'(?:"([^"]*)")|([^"]*)', s)
    result_quoted = [t[0].strip() for t in matches if t[0]]
    result_unquoted = [t[1].strip() for t in matches if t[1]]
    return result_quoted, result_unquoted


def form_query(query_type, query):
    """
    Returns a multi match query
    """
    fields = [
        field + "^" + str(SEARCH_BOOSTS[field]) if field in SEARCH_BOOSTS else field
        for field in SEARCH_FIELDS
    ]
    return Q("multi_match", fields=fields, query=query, type=query_type)


def gather_es_queries(q):
    quoted_string, unquoted_string = filter_query(q)
    must = [form_query("phrase", i) for i in quoted_string] + [
        form_query("best_fields", i) for i in unquoted_string
    ]

    bool_query = Q("bool", must=must)

    # Allow to optionally match on prefix
    # if ``q`` is longer than one character.
    if len(q) > 1:
        bool_query = bool_query | Q("prefix", normalized_name=q)
    return bool_query
