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
from sqlalchemy.orm.exc import NoResultFound

from warehouse.email.ses.models import EmailMessage
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.emails.list",
    renderer="admin/emails/list.html",
    permission="admin",
    uses_session=True,
)
def email_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    email_query = (
        request.db.query(EmailMessage)
               .order_by(EmailMessage.created.desc(),
                         EmailMessage.id))

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(EmailMessage.to.ilike(term))

        email_query = email_query.filter(or_(*filters))

    emails = SQLAlchemyORMPage(
        email_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"emails": emails, "query": q}


@view_config(
    route_name="admin.emails.detail",
    renderer="admin/emails/detail.html",
    permission="admin",
    uses_session=True,
)
def email_detail(request):
    try:
        email = (
            request.db.query(EmailMessage)
                      .filter(EmailMessage.id == request.matchdict["email_id"])
                      .one()
        )
    except NoResultFound:
        raise HTTPNotFound

    return {"email": email}
