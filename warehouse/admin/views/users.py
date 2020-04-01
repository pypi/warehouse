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
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

from warehouse import forms
from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import DisableReason, Email, User
from warehouse.email import send_password_compromised_email
from warehouse.packaging.models import JournalEntry, Project, Role
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.user.list",
    renderer="admin/users/list.html",
    permission="moderator",
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


class EmailForm(forms.Form):

    email = wtforms.fields.html5.EmailField(
        validators=[wtforms.validators.DataRequired()]
    )
    primary = wtforms.fields.BooleanField()
    verified = wtforms.fields.BooleanField()
    public = wtforms.fields.BooleanField()


class UserForm(forms.Form):

    name = wtforms.StringField(
        validators=[wtforms.validators.Optional(), wtforms.validators.Length(max=100)]
    )

    is_active = wtforms.fields.BooleanField()
    is_superuser = wtforms.fields.BooleanField()
    is_moderator = wtforms.fields.BooleanField()

    emails = wtforms.fields.FieldList(wtforms.fields.FormField(EmailForm))


@view_config(
    route_name="admin.user.detail",
    renderer="admin/users/detail.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.user.detail",
    renderer="admin/users/detail.html",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def user_detail(request):
    try:
        user = (
            request.db.query(User).filter(User.id == request.matchdict["user_id"]).one()
        )
    except NoResultFound:
        raise HTTPNotFound

    roles = (
        request.db.query(Role)
        .join(User)
        .filter(Role.user == user)
        .order_by(Role.role_name, Role.project_id)
        .all()
    )

    form = UserForm(request.POST if request.method == "POST" else None, user)

    if request.method == "POST" and form.validate():
        form.populate_obj(user)
        return HTTPSeeOther(location=request.current_route_path())

    return {"user": user, "form": form, "roles": roles, "add_email_form": EmailForm()}


@view_config(
    route_name="admin.user.add_email",
    require_methods=["POST"],
    permission="admin",
    uses_session=True,
    require_csrf=True,
)
def user_add_email(request):
    user = request.db.query(User).get(request.matchdict["user_id"])
    form = EmailForm(request.POST)

    if form.validate():
        email = Email(
            email=form.email.data,
            user=user,
            primary=form.primary.data,
            verified=form.verified.data,
            public=form.public.data,
        )
        request.db.add(email)
        request.session.flash(
            f"Added email for user {user.username!r}", queue="success"
        )

    return HTTPSeeOther(request.route_path("admin.user.detail", user_id=user.id))


@view_config(
    route_name="admin.user.delete",
    require_methods=["POST"],
    permission="admin",
    uses_session=True,
    require_csrf=True,
)
def user_delete(request):
    user = request.db.query(User).get(request.matchdict["user_id"])

    if user.username != request.params.get("username"):
        request.session.flash(f"Wrong confirmation input", queue="error")
        return HTTPSeeOther(request.route_path("admin.user.detail", user_id=user.id))

    # Delete all the user's projects
    projects = request.db.query(Project).filter(
        Project.name.in_(
            request.db.query(Project.name)
            .join(Role.project)
            .filter(Role.user == user)
            .subquery()
        )
    )
    for project in projects:
        request.db.add(
            JournalEntry(
                name=project.name,
                action="remove project",
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )
    projects.delete(synchronize_session=False)

    # Update all journals to point to `deleted-user` instead
    deleted_user = request.db.query(User).filter(User.username == "deleted-user").one()

    journals = (
        request.db.query(JournalEntry)
        .options(joinedload("submitted_by"))
        .filter(JournalEntry.submitted_by == user)
        .all()
    )

    for journal in journals:
        journal.submitted_by = deleted_user

    # Delete the user
    request.db.delete(user)
    request.db.add(
        JournalEntry(
            name=f"user:{user.username}",
            action=f"nuke user",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )
    request.session.flash(f"Nuked user {user.username!r}", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.list"))


@view_config(
    route_name="admin.user.reset_password",
    require_methods=["POST"],
    permission="admin",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def user_reset_password(request):
    user = request.db.query(User).get(request.matchdict["user_id"])

    if user.username != request.params.get("username"):
        request.session.flash(f"Wrong confirmation input", queue="error")
        return HTTPSeeOther(request.route_path("admin.user.detail", user_id=user.id))

    login_service = request.find_service(IUserService, context=None)
    send_password_compromised_email(request, user)
    login_service.disable_password(user.id, reason=DisableReason.CompromisedPassword)

    request.session.flash(f"Reset password for {user.username!r}", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.detail", user_id=user.id))
