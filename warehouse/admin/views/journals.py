# SPDX-License-Identifier: Apache-2.0

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from warehouse.authnz import Permissions
from warehouse.packaging.models import JournalEntry
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.journals.list",
    renderer="admin/journals/list.html",
    permission=Permissions.AdminJournalRead,
    uses_session=True,
)
def journals_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    journals_query = (
        request.db.query(JournalEntry)
        .options(joinedload(JournalEntry.submitted_by))
        .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            if ":" in term:
                field, value = term.split(":", 1)
                if field.lower() == "project":
                    filters.append(JournalEntry.name.ilike(value))
                if field.lower() == "version":
                    filters.append(JournalEntry.version.ilike(value))
                if field.lower() == "user":
                    filters.append(JournalEntry._submitted_by.like(value))
            else:
                filters.append(JournalEntry.name.ilike(term))

        journals_query = journals_query.filter(and_(*filters))

    journals = SQLAlchemyORMPage(
        journals_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"journals": journals, "query": q}
