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
import wtforms.fields
import wtforms.validators

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import literal, or_, select
from sqlalchemy.orm import joinedload

from warehouse import forms
from warehouse.accounts.interfaces import IEmailBreachedService, IUserService
from warehouse.accounts.models import (
    DisableReason,
    Email,
    ProhibitedEmailDomain,
    ProhibitedUserName,
    User,
)
from warehouse.authnz import Permissions
from warehouse.email import send_password_compromised_email
from warehouse.packaging.models import JournalEntry, Project, Role
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.user.list",
    renderer="admin/users/list.html",
    permission=Permissions.AdminUsersRead,
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
                elif field.lower() == "id":
                    filters.append(User.id == value)
            else:
                filters.append(User.username.ilike(term))

        filters = filters or [True]
        users_query = users_query.filter(or_(False, *filters))

    users = SQLAlchemyORMPage(
        users_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"users": users, "query": q}


class EmailForm(forms.Form):
    email = wtforms.fields.EmailField(validators=[wtforms.validators.InputRequired()])
    primary = wtforms.fields.BooleanField()
    verified = wtforms.fields.BooleanField()
    public = wtforms.fields.BooleanField()


class UserForm(forms.Form):
    name = wtforms.StringField(
        validators=[wtforms.validators.Optional(), wtforms.validators.Length(max=100)]
    )

    is_active = wtforms.fields.BooleanField()
    is_frozen = wtforms.fields.BooleanField()
    is_superuser = wtforms.fields.BooleanField()
    is_moderator = wtforms.fields.BooleanField()
    is_psf_staff = wtforms.fields.BooleanField()
    is_observer = wtforms.fields.BooleanField()

    prohibit_password_reset = wtforms.fields.BooleanField()
    hide_avatar = wtforms.fields.BooleanField()

    emails = wtforms.fields.FieldList(wtforms.fields.FormField(EmailForm))

    def validate_emails(self, field):
        # If there's no email on the account, it's ok. Otherwise, ensure
        # we have 1 primary email.
        if field.data and len([1 for email in field.data if email["primary"]]) != 1:
            raise wtforms.validators.ValidationError(
                "There must be exactly one primary email"
            )


@view_config(
    route_name="admin.user.detail",
    renderer="admin/users/detail.html",
    permission=Permissions.AdminUsersRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.user.detail",
    renderer="admin/users/detail.html",
    permission=Permissions.AdminUsersWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    context=User,
)
def user_detail(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

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
        request.session.flash(f"User {user.username!r} updated", queue="success")
        return HTTPSeeOther(location=request.current_route_path())

    # Incurs API call for every email address stored.
    breached_email_count = {
        email_entry.data["email"]: request.find_service(
            IEmailBreachedService
        ).get_email_breach_count(email_entry.data["email"])
        for email_entry in form.emails.entries
    }

    return {
        "user": user,
        "form": form,
        "roles": roles,
        "add_email_form": EmailForm(),
        "breached_email_count": breached_email_count,
    }


@view_config(
    route_name="admin.user.add_email",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_add_email(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    form = EmailForm(request.POST)

    if form.validate():
        if form.primary.data:
            for other in user.emails:
                other.primary = False

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

    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


def _nuke_user(user, request):
    # Delete all the user's projects
    projects = request.db.query(Project).filter(
        Project.name.in_(
            select(Project.name).join(Role.project).where(Role.user == user)
        )
    )
    for project in projects:
        request.db.add(
            JournalEntry(
                name=project.name,
                action="remove project",
                submitted_by=request.user,
            )
        )
    projects.delete(synchronize_session=False)

    # Update all journals to point to `deleted-user` instead
    deleted_user = request.db.query(User).filter(User.username == "deleted-user").one()

    journals = (
        request.db.query(JournalEntry)
        .options(joinedload(JournalEntry.submitted_by))
        .filter(JournalEntry.submitted_by == user)
        .all()
    )

    for journal in journals:
        journal.submitted_by = deleted_user

    # Prohibit the username
    request.db.add(
        ProhibitedUserName(
            name=user.username.lower(), comment="nuked", prohibited_by=request.user
        )
    )

    # Delete the user
    request.db.delete(user)


@view_config(
    route_name="admin.user.delete",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_delete(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    if user.username != request.params.get("username"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    _nuke_user(user, request)

    request.session.flash(f"Nuked user {user.username!r}", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.list"))


@view_config(
    route_name="admin.user.freeze",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_freeze(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    if user.username != request.params.get("username"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    user.is_frozen = True

    for email in user.emails:
        if email.verified:
            request.db.add(
                ProhibitedEmailDomain(
                    domain=email.domain,
                    comment="frozen",
                    prohibited_by=request.user,
                )
            )

    request.session.flash(f"Froze user {user.username!r}", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.list"))


def _user_reset_password(user, request):
    login_service = request.find_service(IUserService, context=None)
    send_password_compromised_email(request, user)
    login_service.disable_password(
        user.id, request, reason=DisableReason.CompromisedPassword
    )


@view_config(
    route_name="admin.user.reset_password",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_reset_password(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    if user.username != request.params.get("username"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    _user_reset_password(user, request)

    request.session.flash(f"Reset password for {user.username!r}", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.user.wipe_factors",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_wipe_factors(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    if user.username != request.params.get("username"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    user.totp_secret = None
    user.webauthn = []
    user.recovery_codes = []
    _user_reset_password(user, request)

    request.session.flash(
        f"Wiped factors and reset password for {user.username!r}", queue="success"
    )
    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.prohibited_user_names.bulk_add",
    renderer="admin/prohibited_user_names/bulk.html",
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_methods=False,
)
def bulk_add_prohibited_user_names(request):
    if request.method == "POST":
        user_names = request.POST.get("users", "").split()

        for user_name in user_names:
            # Check to make sure the prohibition doesn't already exist.
            if (
                request.db.query(literal(True))
                .filter(
                    request.db.query(ProhibitedUserName)
                    .filter(ProhibitedUserName.name == user_name.lower())
                    .exists()
                )
                .scalar()
            ):
                continue

            # Go through and delete the usernames

            user = request.db.query(User).filter(User.username == user_name).first()
            if user is not None:
                _nuke_user(user, request)
            else:
                request.db.add(
                    ProhibitedUserName(
                        name=user_name.lower(),
                        comment="nuked",
                        prohibited_by=request.user,
                    )
                )

        request.session.flash(f"Prohibited {len(user_names)!r} users", queue="success")

        return HTTPSeeOther(request.route_path("admin.prohibited_user_names.bulk_add"))
    return {}
