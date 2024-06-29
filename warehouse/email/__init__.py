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

import datetime
import functools

from email.headerregistry import Address

import pytz
import sentry_sdk

from celery.schedules import crontab
from first import first
from pyramid_mailer.exceptions import BadHeaders, EncodingError, InvalidMessage
from sqlalchemy.exc import NoResultFound

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, IUserService
from warehouse.accounts.models import Email
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import EmailMessage
from warehouse.email.ses.tasks import cleanup as ses_cleanup
from warehouse.events.tags import EventTag
from warehouse.metrics.interfaces import IMetricsService


def _compute_recipient(user, email):
    # We want to try and use the user's name, then their username, and finally
    # nothing to display a "Friendly" name for the recipient.
    return str(Address(first([user.name, user.username], default=""), addr_spec=email))


def _redact_ip(request, email):
    # We should only store/display IP address of an 'email sent' event if the user
    # who triggered the email event is the one who receives the email. Else display
    # 'Redacted' to prevent user privacy concerns. If we don't know the user who
    # triggered the action, default to showing the IP of the source.

    try:
        user_email = request.db.query(Email).filter(Email.email == email).one()
    except NoResultFound:
        # The email might have been deleted if this is an account deletion event
        return False

    if request._unauthenticated_userid:
        return user_email.user_id != request._unauthenticated_userid
    if request.user:
        return user_email.user_id != request.user.id
    if request.remote_addr == "127.0.0.1":
        # This is the IP used when synthesizing a request in a task
        return True
    return False


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def send_email(task, request, recipient, msg, success_event):
    msg = EmailMessage(**msg)
    sender = request.find_service(IEmailSender)

    try:
        sender.send(recipient, msg)
        user_service = request.find_service(IUserService, context=None)
        user = user_service.get_user(success_event.pop("user_id"))
        success_event["request"] = request
        if user is not None:  # We send account deletion confirmation emails
            user.record_event(**success_event)
    except (BadHeaders, EncodingError, InvalidMessage) as exc:
        raise exc
    except Exception as exc:
        # Send any other exception to Sentry, but don't re-raise it
        sentry_sdk.capture_exception(exc)
        task.retry(exc=exc)


def _send_email_to_user(
    request,
    user,
    msg,
    *,
    email=None,
    allow_unverified=False,
    repeat_window=None,
):
    # If we were not given a specific email object, then we'll default to using
    # the User's primary email address.
    if email is None:
        email = user.primary_email

    # If we were not able to locate an email address for this user, then we will just
    # have to skip sending email to them. If we have an email for them, then we will
    # check to see if it is verified, if it is not then we will also skip sending email
    # to them **UNLESS** we've been told to allow unverified emails.
    if email is None or not (email.verified or allow_unverified):
        return

    # If we've already sent this email within the repeat_window, don't send it.
    if repeat_window is not None:
        sender = request.find_service(IEmailSender)
        last_sent = sender.last_sent(to=email.email, subject=msg.subject)
        if last_sent and (datetime.datetime.now() - last_sent) <= repeat_window:
            return

    request.task(send_email).delay(
        _compute_recipient(user, email.email),
        {
            "subject": msg.subject,
            "body_text": msg.body_text,
            "body_html": msg.body_html,
        },
        {
            "tag": EventTag.Account.EmailSent,
            "user_id": user.id,
            "additional": {
                "from_": request.registry.settings.get("mail.sender"),
                "to": email.email,
                "subject": msg.subject,
                "redact_ip": _redact_ip(request, email.email),
            },
        },
    )


def _email(
    name,
    *,
    allow_unverified=False,
    repeat_window=None,
):
    """
    This decorator is used to turn an e function into an email sending function!

    The name parameter is the name of the email we're going to be sending (used to
    locate the templates on the file system).

    The allow_unverified kwarg flags whether we will send this email to an unverified
    email or not. We generally do not want to do this, but some emails are important
    enough or have special requirements that require it.

    Functions that are decorated by this need to accept two positional arguments, the
    first argument is the Pyramid request object, and the second argument is either
    a single User, or a list of Users. These users represent the recipients of this
    email. Additional keyword arguments are supported, but are not otherwise restricted.

    Functions decorated by this must return a mapping of context variables that will
    ultimately be returned, but which will also be used to render the templates for
    the emails.

    Thus this function can decorate functions with a signature like so:

        def foo(
            request: Request, user_or_users: Union[User, List[User]]
        ) -> Mapping[str, Any]:
            ...

    Finally, if the email needs to be sent to an address *other* than the user's primary
    email address, instead of a User object, a tuple of (User, Email) objects may be
    used in place of a User object.
    """

    def inner(fn):
        @functools.wraps(fn)
        def wrapper(request, user_or_users, **kwargs):
            if isinstance(user_or_users, (list, set)):
                recipients = user_or_users
            else:
                recipients = [user_or_users]

            context = fn(request, user_or_users, **kwargs)
            msg = EmailMessage.from_template(name, context, request=request)

            for recipient in recipients:
                if isinstance(recipient, tuple):
                    user, email = recipient
                else:
                    user, email = recipient, None

                _send_email_to_user(
                    request,
                    user,
                    msg,
                    email=email,
                    allow_unverified=allow_unverified,
                    repeat_window=repeat_window,
                )
                metrics = request.find_service(IMetricsService, context=None)
                metrics.increment(
                    "warehouse.emails.scheduled",
                    tags=[
                        f"template_name:{name}",
                        f"allow_unverified:{allow_unverified}",
                        (
                            f"repeat_window:{repeat_window.total_seconds()}"
                            if repeat_window
                            else "repeat_window:none"
                        ),
                    ],
                )

            return context

        return wrapper

    return inner


# Email templates for administrators.


@_email("admin-new-organization-requested")
def send_admin_new_organization_requested_email(
    request, user, *, organization_name, initiator_username, organization_id
):
    return {
        "initiator_username": initiator_username,
        "organization_id": organization_id,
        "organization_name": organization_name,
    }


@_email("admin-new-organization-approved")
def send_admin_new_organization_approved_email(
    request, user, *, organization_name, initiator_username, message=""
):
    return {
        "initiator_username": initiator_username,
        "message": message,
        "organization_name": organization_name,
    }


@_email("admin-new-organization-declined")
def send_admin_new_organization_declined_email(
    request, user, *, organization_name, initiator_username, message=""
):
    return {
        "initiator_username": initiator_username,
        "message": message,
        "organization_name": organization_name,
    }


@_email("admin-organization-renamed")
def send_admin_organization_renamed_email(
    request, user, *, organization_name, previous_organization_name
):
    return {
        "organization_name": organization_name,
        "previous_organization_name": previous_organization_name,
    }


@_email("admin-organization-deleted")
def send_admin_organization_deleted_email(request, user, *, organization_name):
    return {
        "organization_name": organization_name,
    }


# Email templates for users.


@_email("password-reset", allow_unverified=True)
def send_password_reset_email(request, user_and_email):
    user, _ = user_and_email
    token_service = request.find_service(ITokenService, name="password")
    token = token_service.dumps(
        {
            "action": "password-reset",
            "user.id": str(user.id),
            "user.last_login": str(
                user.last_login or datetime.datetime.min.replace(tzinfo=pytz.UTC)
            ),
            "user.password_date": str(
                user.password_date or datetime.datetime.min.replace(tzinfo=pytz.UTC)
            ),
        }
    )

    return {
        "token": token,
        "username": user.username,
        "n_hours": token_service.max_age // 60 // 60,
    }


@_email("verify-email", allow_unverified=True)
def send_email_verification_email(request, user_and_email):
    user, email = user_and_email
    token_service = request.find_service(ITokenService, name="email")
    token = token_service.dumps({"action": "email-verify", "email.id": email.id})

    return {
        "token": token,
        "email_address": email.email,
        "n_hours": token_service.max_age // 60 // 60,
    }


@_email("new-email-added")
def send_new_email_added_email(request, user_and_email, *, new_email_address):
    user, _ = user_and_email

    return {
        "username": user.username,
        "new_email_address": new_email_address,
    }


@_email("password-change")
def send_password_change_email(request, user):
    return {"username": user.username}


@_email("password-compromised", allow_unverified=True)
def send_password_compromised_email(request, user):
    return {}


@_email("password-compromised-hibp", allow_unverified=True)
def send_password_compromised_email_hibp(request, user):
    return {}


@_email("token-compromised-leak", allow_unverified=True)
def send_token_compromised_email_leak(request, user, *, public_url, origin):
    return {"username": user.username, "public_url": public_url, "origin": origin}


@_email(
    "two-factor-not-yet-enabled",
    allow_unverified=True,
    repeat_window=datetime.timedelta(days=14),
)
def send_two_factor_not_yet_enabled_email(request, user):
    return {"username": user.username}


@_email("account-deleted")
def send_account_deletion_email(request, user):
    return {"username": user.username}


@_email("primary-email-change")
def send_primary_email_change_email(request, user_and_email):
    user, email = user_and_email
    return {
        "username": user.username,
        "old_email": email.email,
        "new_email": user.email,
    }


@_email("new-organization-requested")
def send_new_organization_requested_email(request, user, *, organization_name):
    return {"organization_name": organization_name}


@_email("new-organization-approved")
def send_new_organization_approved_email(
    request, user, *, organization_name, message=""
):
    return {
        "message": message,
        "organization_name": organization_name,
    }


@_email("new-organization-declined")
def send_new_organization_declined_email(
    request, user, *, organization_name, message=""
):
    return {
        "message": message,
        "organization_name": organization_name,
    }


@_email("organization-project-added")
def send_organization_project_added_email(
    request, user, *, organization_name, project_name
):
    return {
        "organization_name": organization_name,
        "project_name": project_name,
    }


@_email("organization-project-removed")
def send_organization_project_removed_email(
    request, user, *, organization_name, project_name
):
    return {
        "organization_name": organization_name,
        "project_name": project_name,
    }


@_email("organization-member-invited")
def send_organization_member_invited_email(
    request,
    email_recipients,
    *,
    user,
    desired_role,
    initiator_username,
    organization_name,
    email_token,
    token_age,
):
    return {
        "username": user.username,
        "desired_role": desired_role,
        "initiator_username": initiator_username,
        "n_hours": token_age // 60 // 60,
        "organization_name": organization_name,
        "token": email_token,
    }


@_email("verify-organization-role", allow_unverified=True)
def send_organization_role_verification_email(
    request,
    user,
    *,
    desired_role,
    initiator_username,
    organization_name,
    email_token,
    token_age,
):
    return {
        "username": user.username,
        "desired_role": desired_role,
        "initiator_username": initiator_username,
        "n_hours": token_age // 60 // 60,
        "organization_name": organization_name,
        "token": email_token,
    }


@_email("organization-member-invite-canceled")
def send_organization_member_invite_canceled_email(
    request,
    email_recipients,
    *,
    user,
    organization_name,
):
    return {
        "username": user.username,
        "organization_name": organization_name,
    }


@_email("canceled-as-invited-organization-member")
def send_canceled_as_invited_organization_member_email(
    request,
    user,
    *,
    organization_name,
):
    return {
        "username": user.username,
        "organization_name": organization_name,
    }


@_email("organization-member-invite-declined")
def send_organization_member_invite_declined_email(
    request,
    email_recipients,
    *,
    user,
    organization_name,
    message,
):
    return {
        "username": user.username,
        "organization_name": organization_name,
        "message": message,
    }


@_email("declined-as-invited-organization-member")
def send_declined_as_invited_organization_member_email(
    request,
    user,
    *,
    organization_name,
):
    return {
        "username": user.username,
        "organization_name": organization_name,
    }


@_email("organization-member-added")
def send_organization_member_added_email(
    request,
    email_recipients,
    *,
    user,
    submitter,
    organization_name,
    role,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "role": role,
    }


@_email("added-as-organization-member")
def send_added_as_organization_member_email(
    request,
    user,
    *,
    submitter,
    organization_name,
    role,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "role": role,
    }


@_email("organization-member-removed")
def send_organization_member_removed_email(
    request,
    email_recipients,
    *,
    user,
    submitter,
    organization_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
    }


@_email("removed-as-organization-member")
def send_removed_as_organization_member_email(
    request,
    user,
    *,
    submitter,
    organization_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
    }


@_email("organization-member-role-changed")
def send_organization_member_role_changed_email(
    request,
    email_recipients,
    *,
    user,
    submitter,
    organization_name,
    role,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "role": role,
    }


@_email("role-changed-as-organization-member")
def send_role_changed_as_organization_member_email(
    request,
    user,
    *,
    submitter,
    organization_name,
    role,
):
    return {
        "username": user.username,
        "organization_name": organization_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("organization-updated")
def send_organization_updated_email(
    request,
    user,
    *,
    organization_name,
    organization_display_name,
    organization_link_url,
    organization_description,
    organization_orgtype,
    previous_organization_display_name,
    previous_organization_link_url,
    previous_organization_description,
    previous_organization_orgtype,
):
    return {
        "organization_name": organization_name,
        "organization_display_name": organization_display_name,
        "organization_link_url": organization_link_url,
        "organization_description": organization_description,
        "organization_orgtype": organization_orgtype,
        "previous_organization_display_name": previous_organization_display_name,
        "previous_organization_link_url": previous_organization_link_url,
        "previous_organization_description": previous_organization_description,
        "previous_organization_orgtype": previous_organization_orgtype,
    }


@_email("organization-renamed")
def send_organization_renamed_email(
    request, user, *, organization_name, previous_organization_name
):
    return {
        "organization_name": organization_name,
        "previous_organization_name": previous_organization_name,
    }


@_email("organization-deleted")
def send_organization_deleted_email(request, user, *, organization_name):
    return {
        "organization_name": organization_name,
    }


@_email("team-created")
def send_team_created_email(request, user, *, organization_name, team_name):
    return {
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("team-deleted")
def send_team_deleted_email(request, user, *, organization_name, team_name):
    return {
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("team-member-added")
def send_team_member_added_email(
    request,
    email_recipients,
    *,
    user,
    submitter,
    organization_name,
    team_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("added-as-team-member")
def send_added_as_team_member_email(
    request,
    user,
    *,
    submitter,
    organization_name,
    team_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("team-member-removed")
def send_team_member_removed_email(
    request,
    email_recipients,
    *,
    user,
    submitter,
    organization_name,
    team_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("removed-as-team-member")
def send_removed_as_team_member_email(
    request,
    user,
    *,
    submitter,
    organization_name,
    team_name,
):
    return {
        "username": user.username,
        "submitter": submitter.username,
        "organization_name": organization_name,
        "team_name": team_name,
    }


@_email("verify-project-role", allow_unverified=True)
def send_project_role_verification_email(
    request,
    user,
    desired_role,
    initiator_username,
    project_name,
    email_token,
    token_age,
):
    return {
        "desired_role": desired_role,
        "email_address": user.email,
        "initiator_username": initiator_username,
        "n_hours": token_age // 60 // 60,
        "project_name": project_name,
        "token": email_token,
    }


@_email("collaborator-added")
def send_collaborator_added_email(
    request, email_recipients, *, user, submitter, project_name, role
):
    return {
        "username": user.username,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("added-as-collaborator")
def send_added_as_collaborator_email(request, user, *, submitter, project_name, role):
    return {
        "project_name": project_name,
        "initiator_username": submitter.username,
        "role": role,
    }


@_email("collaborator-removed")
def send_collaborator_removed_email(
    request, email_recipients, *, user, submitter, project_name
):
    return {
        "username": user.username,
        "project": project_name,
        "submitter": submitter.username,
    }


@_email("removed-as-collaborator")
def send_removed_as_collaborator_email(request, user, *, submitter, project_name):
    return {
        "project": project_name,
        "submitter": submitter.username,
    }


@_email("collaborator-role-changed")
def send_collaborator_role_changed_email(
    request, recipients, *, user, submitter, project_name, role
):
    return {
        "username": user.username,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("role-changed-as-collaborator")
def send_role_changed_as_collaborator_email(
    request, user, *, submitter, project_name, role
):
    return {
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("team-collaborator-added")
def send_team_collaborator_added_email(
    request, email_recipients, *, team, submitter, project_name, role
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("added-as-team-collaborator")
def send_added_as_team_collaborator_email(
    request, email_recipients, *, team, submitter, project_name, role
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("team-collaborator-removed")
def send_team_collaborator_removed_email(
    request, email_recipients, *, team, submitter, project_name
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
    }


@_email("removed-as-team-collaborator")
def send_removed_as_team_collaborator_email(
    request, email_recipients, *, team, submitter, project_name
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
    }


@_email("team-collaborator-role-changed")
def send_team_collaborator_role_changed_email(
    request, email_recipients, *, team, submitter, project_name, role
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("role-changed-as-team-collaborator")
def send_role_changed_as_team_collaborator_email(
    request, email_recipients, *, team, submitter, project_name, role
):
    return {
        "team_name": team.name,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }


@_email("two-factor-added")
def send_two_factor_added_email(request, user, method):
    pretty_methods = {"totp": "TOTP", "webauthn": "WebAuthn"}
    return {"method": pretty_methods[method], "username": user.username}


@_email("two-factor-removed")
def send_two_factor_removed_email(request, user, method):
    pretty_methods = {"totp": "TOTP", "webauthn": "WebAuthn"}
    return {"method": pretty_methods[method], "username": user.username}


@_email("removed-project")
def send_removed_project_email(
    request, user, *, project_name, submitter_name, submitter_role, recipient_role
):
    recipient_role_descr = "an owner"
    if recipient_role == "Maintainer":
        recipient_role_descr = "a maintainer"

    return {
        "project_name": project_name,
        "submitter_name": submitter_name,
        "submitter_role": submitter_role.lower(),
        "recipient_role_descr": recipient_role_descr,
    }


@_email("yanked-project-release")
def send_yanked_project_release_email(
    request, user, *, release, submitter_name, submitter_role, recipient_role
):
    recipient_role_descr = "an owner"
    if recipient_role == "Maintainer":
        recipient_role_descr = "a maintainer"

    return {
        "project": release.project.name,
        "release": release.version,
        "release_date": release.created.strftime("%Y-%m-%d"),
        "submitter": submitter_name,
        "submitter_role": submitter_role.lower(),
        "recipient_role_descr": recipient_role_descr,
        "yanked_reason": release.yanked_reason,
    }


@_email("unyanked-project-release")
def send_unyanked_project_release_email(
    request, user, *, release, submitter_name, submitter_role, recipient_role
):
    recipient_role_descr = "an owner"
    if recipient_role == "Maintainer":
        recipient_role_descr = "a maintainer"

    return {
        "project": release.project.name,
        "release": release.version,
        "release_date": release.created.strftime("%Y-%m-%d"),
        "submitter": submitter_name,
        "submitter_role": submitter_role.lower(),
        "recipient_role_descr": recipient_role_descr,
    }


@_email("removed-project-release")
def send_removed_project_release_email(
    request, user, *, release, submitter_name, submitter_role, recipient_role
):
    recipient_role_descr = "an owner"
    if recipient_role == "Maintainer":
        recipient_role_descr = "a maintainer"

    return {
        "project_name": release.project.name,
        "release_version": release.version,
        "release_date": release.created.strftime("%Y-%m-%d"),
        "submitter_name": submitter_name,
        "submitter_role": submitter_role.lower(),
        "recipient_role_descr": recipient_role_descr,
    }


@_email("removed-project-release-file")
def send_removed_project_release_file_email(
    request, user, *, file, release, submitter_name, submitter_role, recipient_role
):
    recipient_role_descr = "an owner"
    if recipient_role == "Maintainer":
        recipient_role_descr = "a maintainer"

    return {
        "file": file,
        "project_name": release.project.name,
        "release_version": release.version,
        "submitter_name": submitter_name,
        "submitter_role": submitter_role.lower(),
        "recipient_role_descr": recipient_role_descr,
    }


@_email("recovery-codes-generated")
def send_recovery_codes_generated_email(request, user):
    return {"username": user.username}


@_email("recovery-code-used")
def send_recovery_code_used_email(request, user):
    return {"username": user.username}


@_email("recovery-code-reminder")
def send_recovery_code_reminder_email(request, user):
    return {"username": user.username}


@_email("trusted-publisher-added")
def send_trusted_publisher_added_email(request, user, project_name, publisher):
    # We use the request's user, since they're the one triggering the action.
    return {
        "username": request.user.username,
        "project_name": project_name,
        "publisher": publisher,
    }


@_email("trusted-publisher-removed")
def send_trusted_publisher_removed_email(request, user, project_name, publisher):
    # We use the request's user, since they're the one triggering the action.
    return {
        "username": request.user.username,
        "project_name": project_name,
        "publisher": publisher,
    }


@_email("pending-trusted-publisher-invalidated")
def send_pending_trusted_publisher_invalidated_email(request, user, project_name):
    return {
        "project_name": project_name,
    }


@_email("api-token-used-in-trusted-publisher-project")
def send_api_token_used_in_trusted_publisher_project_email(
    request, users, project_name, token_owner_username, token_name
):
    return {
        "token_owner_username": token_owner_username,
        "project_name": project_name,
        "token_name": token_name,
    }


def includeme(config):
    email_sending_class = config.maybe_dotted(config.registry.settings["mail.backend"])
    config.register_service_factory(email_sending_class.create_service, IEmailSender)

    # Add a periodic task to cleanup our EmailMessage table. We're going to
    # do this cleanup, regardless of if we're configured to use SES to send
    # or not, because even if we stop using SES, we'll want to remove any
    # emails that had been sent, and the cost of doing this is very low.
    config.add_periodic_task(crontab(minute=0, hour=0), ses_cleanup)
