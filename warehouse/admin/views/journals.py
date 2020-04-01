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
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from warehouse.packaging.models import JournalEntry
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.journals.list",
    renderer="admin/journals/list.html",
    permission="moderator",
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
                if field.lower() == "ip":
                    filters.append(JournalEntry.submitted_from.ilike(value))
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
