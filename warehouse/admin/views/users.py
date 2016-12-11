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

import wtforms
import wtforms.fields.html5

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPSeeOther, HTTPBadRequest, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import or_
from sqlalchemy.orm.exc import NoResultFound

from warehouse import forms
from warehouse.accounts.models import User, Email
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.user.list",
    renderer="admin/users/list.html",
    permission="admin",
    uses_session=True,
)
def user_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    users_query = request.db.query(User).order_by(User.username)

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            if ":" in term:
                field, value = term.split(":", 1)
                if field.lower() == "email":
                    filters.append(User.emails.any(Email.email.ilike(value)))
            else:
                filters.append(User.username.ilike(term))

        users_query = users_query.filter(or_(*filters))

    users = SQLAlchemyORMPage(
        users_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"users": users, "query": q}


class EmailField(forms.Form):

    email = wtforms.fields.html5.EmailField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Email(),
        ],
    )
    primary = wtforms.fields.BooleanField()
    verified = wtforms.fields.BooleanField()


class UserForm(forms.Form):

    name = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Length(max=100),
        ],
    )

    is_active = wtforms.fields.BooleanField()
    is_superuser = wtforms.fields.BooleanField()

    emails = wtforms.fields.FieldList(wtforms.fields.FormField(EmailField))


@view_config(route_name="admin.user.detail",
             renderer="admin/users/detail.html",
             permission="admin",
             uses_session=True,
             require_csrf=True,
             require_methods=False)
def user_detail(request):
    try:
        user = (
            request.db.query(User)
                      .filter(User.id == request.matchdict["user_id"])
                      .one()
        )
    except NoResultFound:
        raise HTTPNotFound

    form = UserForm(request.POST, user)

    if request.method == "POST" and form.validate():
        form.populate_obj(user)
        return HTTPSeeOther(location=request.current_route_path())

    return {"user": user, "form": form}
