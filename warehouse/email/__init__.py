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

import functools

from email.headerregistry import Address

import attr

from celery.schedules import crontab
from first import first

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import EmailMessage
from warehouse.email.ses.tasks import cleanup as ses_cleanup


def _compute_recipient(user, email):
    # We want to try and use the user's name, then their username, and finally
    # nothing to display a "Friendly" name for the recipient.
    return str(Address(first([user.name, user.username], default=""), addr_spec=email))


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def send_email(task, request, recipient, msg):
    msg = EmailMessage(**msg)
    sender = request.find_service(IEmailSender)

    try:
        sender.send(recipient, msg)
    except Exception as exc:
        task.retry(exc=exc)


def _send_email_to_user(request, user, msg, *, email=None, allow_unverified=False):
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

    request.task(send_email).delay(
        _compute_recipient(user, email.email), attr.asdict(msg)
    )


def _email(name, *, allow_unverified=False):
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
                    request, user, msg, email=email, allow_unverified=allow_unverified
                )

            return context

        return wrapper

    return inner


@_email("password-reset", allow_unverified=True)
def send_password_reset_email(request, user_and_email):
    user, _ = user_and_email
    token_service = request.find_service(ITokenService, name="password")
    token = token_service.dumps(
        {
            "action": "password-reset",
            "user.id": str(user.id),
            "user.last_login": str(user.last_login),
            "user.password_date": str(user.password_date),
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


@_email("password-change")
def send_password_change_email(request, user):
    return {"username": user.username}


@_email("password-compromised", allow_unverified=True)
def send_password_compromised_email(request, user):
    return {}


@_email("password-compromised-hibp", allow_unverified=True)
def send_password_compromised_email_hibp(request, user):
    return {}


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
    return {"project": project_name, "submitter": submitter.username, "role": role}


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
        "project": project_name,
        "submitter": submitter_name,
        "submitter_role": submitter_role,
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
        "project": release.project.name,
        "release": release.version,
        "release_date": release.created.strftime("%Y-%m-%d"),
        "submitter": submitter_name,
        "submitter_role": submitter_role,
        "recipient_role_descr": recipient_role_descr,
    }


def includeme(config):
    email_sending_class = config.maybe_dotted(config.registry.settings["mail.backend"])
    config.register_service_factory(email_sending_class.create_service, IEmailSender)

    # Add a periodic task to cleanup our EmailMessage table. We're going to
    # do this cleanup, regardless of if we're configured to use SES to send
    # or not, because even if we stop using SES, we'll want to remove any
    # emails that had been sent, and the cost of doing this is very low.
    config.add_periodic_task(crontab(minute=0, hour=0), ses_cleanup)
