# Copyright 2013 Donald Stufft
#
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

import functools

from werkzeug.exceptions import NotFound

from warehouse.helpers import url_for
from warehouse.templates import render_response
from warehouse.utils import SearchPagination


def search(app, request, doctype):
    if doctype not in app.search.types:
        raise NotFound

    limit = app.search.types[doctype].SEARCH_LIMIT

    query = request.args.get("q")
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        raise NotFound
    if page <= 0:
        page = 1
    offset = (page - 1) * limit

    results = app.search.types[doctype].search(query, limit, offset)
    total = results.get("hits", {}).get("total", 0)

    url_partial = functools.partial(
        url_for, request, 'warehouse.search.views.search', doctype='project',
        q=query)
    pages = SearchPagination(page, total, limit, url_partial)

    return render_response(
        app,
        request,
        "search/results.html",
        query=query, total=total, pages=pages,
        results=[r["_source"] for r in results["hits"]["hits"]],
    )
