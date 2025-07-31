# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import shlex
import typing

from collections import defaultdict
from secrets import token_urlsafe

import wtforms
import wtforms.fields
import wtforms.validators

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    IEmailBreachedService,
    InvalidRecoveryCode,
    IUserService,
)
from warehouse.accounts.models import (
    DisableReason,
    Email,
    ProhibitedEmailDomain,
    ProhibitedUserName,
    User,
)
from warehouse.accounts.utils import update_email_domain_status
from warehouse.authnz import Permissions
from warehouse.email import (
    send_account_recovery_initiated_email,
    send_password_reset_by_admin_email,
)
from warehouse.observations.models import ObservationKind
from warehouse.packaging.models import JournalEntry, Project, Release, Role
from warehouse.utils.paginate import paginate_url_factory

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@view_config(
    route_name="admin.user.list",
    renderer="warehouse.admin:templates/admin/users/list.html",
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


class EmailForm(wtforms.Form):
    email = wtforms.fields.EmailField(validators=[wtforms.validators.InputRequired()])
    primary = wtforms.fields.BooleanField()
    verified = wtforms.fields.BooleanField()
    public = wtforms.fields.BooleanField()
    unverify_reason = wtforms.fields.StringField(render_kw={"readonly": True})
    domain_last_checked = wtforms.fields.DateTimeField(render_kw={"readonly": True})
    domain_last_status = wtforms.fields.StringField(render_kw={"readonly": True})


class EmailsForm(wtforms.Form):
    emails = wtforms.fields.FieldList(wtforms.fields.FormField(EmailForm))

    def validate_emails(self, field):
        # If there's no email on the account, it's ok. Otherwise, ensure
        # we have 1 primary email.
        if field.data and len([1 for email in field.data if email["primary"]]) != 1:
            raise wtforms.validators.ValidationError(
                "There must be exactly one primary email"
            )


class UserForm(wtforms.Form):
    name = wtforms.StringField(
        validators=[wtforms.validators.Optional(), wtforms.validators.Length(max=100)]
    )

    is_active = wtforms.fields.BooleanField()
    is_frozen = wtforms.fields.BooleanField()
    is_superuser = wtforms.fields.BooleanField()
    is_support = wtforms.fields.BooleanField()
    is_moderator = wtforms.fields.BooleanField()
    is_psf_staff = wtforms.fields.BooleanField()
    is_observer = wtforms.fields.BooleanField()

    prohibit_password_reset = wtforms.fields.BooleanField()
    hide_avatar = wtforms.fields.BooleanField()


@view_config(
    route_name="admin.user.detail",
    renderer="warehouse.admin:templates/admin/users/detail.html",
    permission=Permissions.AdminUsersRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.user.detail",
    renderer="warehouse.admin:templates/admin/users/detail.html",
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
    emails_form = EmailsForm(request.POST if request.method == "POST" else None, user)

    if request.method == "POST" and form.validate():
        form.populate_obj(user)
        request.session.flash(f"User {user.username!r} updated", queue="success")
        return HTTPSeeOther(location=request.current_route_path())

    # Incurs API call for every email address stored.
    breached_email_count = {
        email_entry.data["email"]: request.find_service(
            IEmailBreachedService
        ).get_email_breach_count(email_entry.data["email"])
        for email_entry in emails_form.emails.entries
    }

    # Get recent Journal entries submitted by this username
    submitted_by_journals = (
        request.db.query(JournalEntry)
        .filter(JournalEntry.submitted_by == user)
        .order_by(JournalEntry.submitted_date.desc())
        .limit(50)
        .all()
    )

    stmt = (
        select(
            Project.name,
            Project.normalized_name,
            Project.lifecycle_status,
            Project.total_size,
            Role.role_name,
            func.count(Release.id),
        )
        .join(Role, Project.id == Role.project_id)
        .outerjoin(Release, Project.id == Release.project_id)
        .where(Role.user_id == user.id)
        .group_by(
            Project.name,
            Project.normalized_name,
            Project.lifecycle_status,
            Project.total_size,
            Role.role_name,
        )
        .order_by(Project.normalized_name.asc())
    )

    user_projects = []

    for row in request.db.execute(stmt):
        project = {
            "name": row.name,
            "normalized_name": row.normalized_name,
            "lifecycle_status": row.lifecycle_status,
            "total_size": row.total_size,
            "role_name": row.role_name,
            "releases_count": row.count,
        }

        user_projects.append(project)

    return {
        "user": user,
        "user_projects": user_projects,
        "form": form,
        "emails_form": emails_form,
        "roles": roles,
        "add_email_form": EmailForm(),
        "breached_email_count": breached_email_count,
        "submitted_by_journals": submitted_by_journals,
    }


@view_config(
    route_name="admin.user.submit_email",
    require_methods=["POST"],
    permission=Permissions.AdminUsersEmailWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_submit_email(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(
            request.route_path("admin.user.detail", username=user.username)
        )

    emails_form = EmailsForm(request.POST if request.method == "POST" else None, user)

    if emails_form.validate():
        emails_form.populate_obj(user)
        request.session.flash(
            f"User {user.username!r}: emails updated", queue="success"
        )
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    for field, error in emails_form.errors.items():
        request.session.flash(f"{field}: {error}", queue="error")

    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.user.add_email",
    require_methods=["POST"],
    permission=Permissions.AdminUsersEmailWrite,
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


@view_config(
    route_name="admin.user.delete_email",
    require_methods=["POST"],
    permission=Permissions.AdminUsersEmailWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_email_delete(user: User, request: Request) -> HTTPSeeOther:
    email = request.db.scalar(
        select(Email).where(
            Email.email == request.POST.get("email_address"), Email.user == user
        )
    )
    if not email:
        request.session.flash("Email not found", queue="error")
        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    request.db.delete(email)
    request.session.flash(f"Email address {email.email!r} deleted", queue="success")
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
    send_password_reset_by_admin_email(request, user)
    login_service.disable_password(
        user.id, request, reason=DisableReason.AdminInitiated
    )


@view_config(
    route_name="admin.user.reset_password",
    require_methods=["POST"],
    permission=Permissions.AdminUsersAccountRecoveryWrite,
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


def _is_a_valid_url(url):
    return url.startswith("https://") or url.startswith("http://")


def _get_related_urls(user):
    project_to_urls = defaultdict(set)
    for project in user.projects:
        if project.releases:
            release = project.releases[0]

            for kind, url in release.urls.items():
                if _is_a_valid_url(url):
                    project_to_urls[project.name].add((kind, url))

    return dict(project_to_urls)


@view_config(
    route_name="admin.user.account_recovery.initiate",
    renderer="warehouse.admin:templates/admin/users/account_recovery/initiate.html",
    permission=Permissions.AdminUsersAccountRecoveryWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    context=User,
    require_methods=False,
)
def user_recover_account_initiate(user, request):
    if user.active_account_recoveries:
        request.session.flash(
            "Only one account recovery may be in process for each user.", queue="error"
        )

        return HTTPSeeOther(
            request.route_path("admin.user.detail", username=user.username)
        )

    repo_urls = _get_related_urls(user)

    if request.method == "POST":

        support_issue_link = request.POST.get("support_issue_link")
        project_name = request.POST.get("project_name")

        if not support_issue_link:
            request.session.flash(
                "Provide a link to the pypi/support issue", queue="error"
            )
        elif not support_issue_link.startswith(
            "https://github.com/pypi/support/issues/"
        ):
            request.session.flash(
                "The pypi/support issue link is invalid", queue="error"
            )
        elif repo_urls and not project_name:
            request.session.flash("Select a project for verification", queue="error")
        else:
            token = token_urlsafe().replace("-", "").replace("_", "")[:16]
            override_to_email = (
                request.POST.get("override_to_email")
                if request.POST.get("override_to_email") != ""
                else None
            )

            if override_to_email is not None:
                user_service = request.find_service(IUserService, context=None)
                _user = user_service.get_user_by_email(override_to_email)
                if _user is None:
                    user_and_email = (
                        user,
                        user_service.add_email(
                            user.id, override_to_email, ratelimit=False
                        ),
                    )
                elif _user != user:
                    request.session.flash(
                        "Email address already associated with a user", queue="error"
                    )
                    return HTTPSeeOther(
                        request.route_path(
                            "admin.user.account_recovery.initiate",
                            username=user.username,
                        )
                    )
                else:
                    user_and_email = (
                        user,
                        request.db.query(Email)
                        .filter(Email.email == override_to_email)
                        .one(),
                    )
            else:
                user_and_email = (user, user.primary_email)

            # Store an event
            observation = user.record_observation(
                request=request,
                kind=ObservationKind.AccountRecovery,
                actor=request.user,
                summary="Account Recovery",
                payload={
                    "initiated": str(datetime.datetime.now(datetime.UTC)),
                    "completed": None,
                    "token": token,
                    "project_name": project_name,
                    "repos": sorted(list(repo_urls.get(project_name, []))),
                    "support_issue_link": support_issue_link,
                    "override_to_email": override_to_email,
                },
            )
            observation.additional = {"status": "initiated"}

            # Send the email
            send_account_recovery_initiated_email(
                request,
                user_and_email,
                project_name=project_name,
                support_issue_link=support_issue_link,
                token=token,
            )

            request.session.flash(
                f"Initiatied account recovery for {user.username!r}", queue="success"
            )

            return HTTPSeeOther(
                request.route_path("admin.user.detail", username=user.username)
            )

        return HTTPSeeOther(
            request.route_path(
                "admin.user.account_recovery.initiate", username=user.username
            )
        )

    return {
        "user": user,
        "repo_urls": repo_urls,
    }


@view_config(
    route_name="admin.user.account_recovery.cancel",
    require_methods=["POST"],
    permission=Permissions.AdminUsersAccountRecoveryWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_recover_account_cancel(user, request):
    for account_recovery in user.active_account_recoveries:
        account_recovery.additional["status"] = "cancelled"
        account_recovery.payload["cancelled"] = str(datetime.datetime.now(datetime.UTC))
    request.session.flash(
        f"Cancelled account recovery for {user.username!r}", queue="success"
    )

    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.user.account_recovery.complete",
    require_methods=["POST"],
    permission=Permissions.AdminUsersAccountRecoveryWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_recover_account_complete(user: User, request):
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

    for account_recovery in user.active_account_recoveries:
        account_recovery.additional["status"] = "completed"
        account_recovery.payload["completed"] = str(datetime.datetime.now(datetime.UTC))
        # Set the primary email to the override email if it exists, and mark as verified
        if override_to_email := account_recovery.payload.get("override_to_email"):
            for email in user.emails:
                email.primary = False  # un-primary any others, so we have only one
                if email.email == override_to_email:
                    email.primary = True
                    email.verified = True

    _user_reset_password(user, request)

    request.session.flash(
        (
            "Account Recovery Complete, "
            f"wiped factors and reset password for {user.username!r}"
        ),
        queue="success",
    )
    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.user.burn_recovery_codes",
    require_methods=["POST"],
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_burn_recovery_codes(user, request):
    codes = request.POST.get("to_burn", "").strip().split()
    if not codes:
        request.session.flash("No recovery codes provided", queue="error")

    else:
        user_service = request.find_service(IUserService, context=None)
        n_burned = 0

        for code in codes:
            try:
                user_service.check_recovery_code(user.id, code, skip_ratelimits=True)
                n_burned += 1
            except (BurnedRecoveryCode, InvalidRecoveryCode):
                pass

        request.session.flash(f"Burned {n_burned} recovery code(s)", queue="success")
    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))


@view_config(
    route_name="admin.user.email_domain_check",
    require_methods=["POST"],
    permission=Permissions.AdminUsersEmailWrite,
    uses_session=True,
    require_csrf=True,
    context=User,
)
def user_email_domain_check(user, request):
    """
    Run a status check on the email domain of the user.
    """
    email_address = request.params.get("email_address")
    email = request.db.scalar(select(Email).where(Email.email == email_address))

    update_email_domain_status(email, request)

    request.session.flash(
        f"Domain status check for {email.domain!r} completed", queue="success"
    )
    return HTTPSeeOther(request.route_path("admin.user.detail", username=user.username))
