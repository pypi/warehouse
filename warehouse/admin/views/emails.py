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

import csv
import io
import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import String, cast, or_
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.email import send_email
from warehouse.email.ses.models import EmailMessage
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.emails.list",
    renderer="admin/emails/list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def email_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    email_query = request.db.query(EmailMessage).order_by(
        EmailMessage.created.desc(), EmailMessage.id
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            if ":" in term:
                field, value = term.split(":", 1)
                if field.lower() == "to":
                    filters.append(EmailMessage.to.ilike(value))
                if field.lower() == "from":
                    filters.append(EmailMessage.from_.ilike(value))
                if field.lower() == "subject":
                    filters.append(EmailMessage.subject.ilike(value))
                if field.lower() == "status":
                    filters.append(cast(EmailMessage.status, String).ilike(value))
            else:
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
    route_name="admin.emails.mass",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def email_mass(request):
    input_file = request.params["csvfile"].file
    wrapper = io.TextIOWrapper(input_file, encoding="utf-8")
    rows = list(csv.DictReader(wrapper))
    if rows:
        for row in rows:
            user = request.db.query(User).get(row["user_id"])
            email = user.primary_email

            if email:
                request.task(send_email).delay(
                    email.email,
                    {
                        "subject": row["subject"],
                        "body_text": row["body_text"],
                        "body_html": row.get("body_html"),
                    },
                    {
                        "sending_user_id": user.id,
                        "ip_address": request.remote_addr,
                        "additional": {
                            "from_": request.registry.settings.get("mail.sender"),
                            "to": email.email,
                            "subject": row["subject"],
                            "redact_ip": True,
                        },
                    },
                )
        request.session.flash("Mass emails sent", queue="success")
    else:
        request.session.flash("No emails to send", queue="error")
    return HTTPSeeOther(request.route_path("admin.emails.list"))


@view_config(
    route_name="admin.emails.detail",
    renderer="admin/emails/detail.html",
    permission="moderator",
    request_method="GET",
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
