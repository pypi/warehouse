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

import elasticsearch

from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPMovedPermanently,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPServiceUnavailable,
    exception_response,
)
from pyramid.i18n import make_localizer
from pyramid.interfaces import ITranslationDirectories
from pyramid.renderers import render_to_response
from pyramid.response import Response
from pyramid.view import (
    exception_view_config,
    forbidden_view_config,
    notfound_view_config,
    view_config,
)
from sqlalchemy import func
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import exists, expression
from trove_classifiers import deprecated_classifiers, sorted_classifiers

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.models import User
from warehouse.cache.http import add_vary, cache_control
from warehouse.cache.origin import origin_cache
from warehouse.classifiers.models import Classifier
from warehouse.db import DatabaseNotAvailable
from warehouse.forms import SetLocaleForm
from warehouse.i18n import LOCALE_ATTR
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import File, Project, Release, release_classifiers
from warehouse.search.queries import SEARCH_FILTER_ORDER, get_es_query
from warehouse.utils.http import is_safe_url
from warehouse.utils.paginate import ElasticsearchPage, paginate_url_factory
from warehouse.utils.row_counter import RowCount


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
    has_translations=True,
)
def index(request):
    project_ids = [
        r[0]
        for r in (
            request.db.query(Project.id)
            .order_by(Project.zscore.desc().nullslast(), func.random())
            .limit(5)
            .all()
        )
    ]
    release_a = aliased(
        Release,
        request.db.query(Release)
        .distinct(Release.project_id)
        .filter(Release.project_id.in_(project_ids))
        .order_by(
            Release.project_id,
            Release.is_prerelease.nullslast(),
            Release._pypi_ordering.desc(),
        )
        .subquery(),
    )
    trending_projects = (
        request.db.query(release_a)
        .options(joinedload(release_a.project))
        .order_by(func.array_idx(project_ids, release_a.project_id))
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


@view_config(
    route_name="locale",
    request_method="GET",
    request_param=SetLocaleForm.__params__,
    uses_session=True,
)
def locale(request):
    form = SetLocaleForm(**request.GET)

    redirect_to = request.referer
    if not is_safe_url(redirect_to, host=request.host):
        redirect_to = request.route_path("index")
    resp = HTTPSeeOther(redirect_to)

    if form.validate():
        # Build a localizer for the locale we're about to switch to. This will
        # happen automatically once the cookie is set, but if we want the flash
        # message indicating success to be in the new language as well, we need
        # to do it here.
        tdirs = request.registry.queryUtility(ITranslationDirectories)
        _ = make_localizer(form.locale_id.data, tdirs).translate
        request.session.flash(_("Locale updated"), queue="success")
        resp.set_cookie(LOCALE_ATTR, form.locale_id.data)

    return resp


@view_config(
    route_name="classifiers", renderer="pages/classifiers.html", has_translations=True
)
def list_classifiers(request):
    return {"classifiers": sorted_classifiers}


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
    has_translations=True,
)
def search(request):
    metrics = request.find_service(IMetricsService, context=None)

    querystring = request.params.get("q", "").replace("'", '"')
    order = request.params.get("o", "")
    classifiers = request.params.getall("c")
    query = get_es_query(request.es, querystring, order, classifiers)

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
        .filter(
            exists([release_classifiers.c.trove_id]).where(
                release_classifiers.c.trove_id == Classifier.id
            ),
            Classifier.classifier.notin_(deprecated_classifiers.keys()),
        )
        .order_by(
            expression.case(
                {c: i for i, c in enumerate(sorted_classifiers)},
                value=Classifier.classifier,
            )
        )
    )

    for cls in classifiers_q:
        first, *_ = cls.classifier.split(" :: ")
        available_filters[first].append(cls.classifier)

    def filter_key(item):
        try:
            return 0, SEARCH_FILTER_ORDER.index(item[0]), item[0]
        except ValueError:
            return 1, 0, item[0]

    def form_filters_tree(split_list):
        """
        Takes a list of lists, each of them containing a filter and
        one of its children.
        Returns a dictionary, each key being a filter and each value being
        the filter's children.
        """
        d = {}
        for list_ in split_list:
            current_level = d
            for part in list_:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        return d

    def process_available_filters():
        """
        Processes available filters and returns a list of dictionaries.
        The value of a key in the dictionary represents its children
        """
        sorted_filters = sorted(available_filters.items(), key=filter_key)
        output = []
        for f in sorted_filters:
            classifier_list = f[1]
            split_list = [i.split(" :: ") for i in classifier_list]
            tree = form_filters_tree(split_list)
            output.append(tree)
        return output

    metrics = request.find_service(IMetricsService, context=None)
    metrics.histogram("warehouse.views.search.results", page.item_count)

    return {
        "page": page,
        "term": querystring,
        "order": order,
        "available_filters": process_available_filters(),
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
    has_translations=True,
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
    total_size = int(request.db.query(func.sum(Project.total_size)).first()[0])
    top_100_packages = (
        request.db.query(Project)
        .with_entities(Project.name, Project.total_size)
        .order_by(Project.total_size.desc().nullslast())
        .limit(100)
        .all()
    )
    # Move top packages into a dict to make JSON more self describing
    top_packages = {
        pkg_name: {"size": int(pkg_bytes) if pkg_bytes is not None else 0}
        for pkg_name, pkg_bytes in top_100_packages
    }

    return {"total_packages_size": total_size, "top_packages": top_packages}


@view_config(
    route_name="includes.current-user-indicator",
    renderer="includes/current-user-indicator.html",
    uses_session=True,
    has_translations=True,
)
def current_user_indicator(request):
    return {}


@view_config(
    route_name="includes.flash-messages",
    renderer="includes/flash-messages.html",
    uses_session=True,
    has_translations=True,
)
def flash_messages(request):
    return {}


@view_config(
    route_name="includes.session-notifications",
    renderer="includes/session-notifications.html",
    uses_session=True,
    has_translations=True,
)
def session_notifications(request):
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
