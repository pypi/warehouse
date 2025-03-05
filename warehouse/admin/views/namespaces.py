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

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import or_

from warehouse.authnz import Permissions
from warehouse.organizations.models import Namespace, Organization
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.namespace.list",
    renderer="admin/namespaces/list.html",
    permission=Permissions.AdminNamespacesRead,
    uses_session=True,
)
def namespace_list(request):
    q = request.params.get("q", "")
    terms = shlex.split(q)

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    query = (
        request.db.query(Namespace)
        .join(Namespace.owner)
        .order_by(Namespace.normalized_name)
    )

    if q:
        filters: list = []
        for term in terms:
            # Examples:
            # - search individual words or "whole phrase" in any field
            # - name:psf
            # - org:python
            # - organization:python
            # - is:approved
            # - is:pending
            try:
                field, value = term.lower().split(":", 1)
            except ValueError:
                field, value = "", term
            if field == "name":
                # Add filter for `name` or `normalized_name` fields.
                filters.append(
                    [
                        Namespace.name.ilike(f"%{value}%"),
                        Namespace.normalized_name.ilike(f"%{value}%"),
                    ]
                )
            elif field == "org" or field == "organization":
                # Add filter for `Organization.Name` or `Organization.normalized_name`
                # field.
                filters.append(
                    [
                        Organization.name.ilike(f"%{value}%"),
                        Organization.normalized_name.ilike(f"%{value}%"),
                    ]
                )
            elif field == "is":
                # Add filter for `is_approved` field.
                if "approved".startswith(value):
                    filters.append(Namespace.is_approved == True)  # noqa: E712
                elif "pending".startswith(value):
                    filters.append(Namespace.is_approved == False)  # noqa: E712
            else:
                # Add filter for any field.
                filters.append(
                    [
                        Namespace.name.ilike(f"%{term}%"),
                        Namespace.normalized_name.ilike(f"%{term}%"),
                    ]
                )
        # Use AND to add each filter. Use OR to combine subfilters.
        for filter_or_subfilters in filters:
            if isinstance(filter_or_subfilters, list):
                # Add list of subfilters combined with OR.
                filter_or_subfilters = filter_or_subfilters or [True]
                query = query.filter(or_(False, *filter_or_subfilters))
            else:
                # Add single filter.
                query = query.filter(filter_or_subfilters)

    namespaces = SQLAlchemyORMPage(
        query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"namespaces": namespaces, "query": q, "terms": terms}


@view_config(
    route_name="admin.namespace.detail",
    require_methods=False,
    renderer="admin/namespaces/detail.html",
    permission=Permissions.AdminNamespacesRead,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def namespace_detail(request):
    namespace = (
        request.db.query(Namespace)
        .join(Namespace.owner)
        .filter(Namespace.id == request.matchdict["namespace_id"])
        .first()
    )
    if namespace is None:
        raise HTTPNotFound

    return {
        "namespace": namespace,
    }
