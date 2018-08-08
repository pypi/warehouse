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


def send_password_reset_email(request, user):
    token_service = request.find_service(ITokenService, name="password")
    token = token_service.dumps(
        {
            "action": "password-reset",
            "user.id": str(user.id),
            "user.last_login": str(user.last_login),
            "user.password_date": str(user.password_date),
        }
    )

    fields = {
        "token": token,
        "username": user.username,
        "n_hours": token_service.max_age // 60 // 60,
    }

    msg = EmailMessage.from_template("password-reset", fields, request=request)

    _send_email_to_user(request, user, msg, allow_unverified=True)

    # Return the fields we used, in case we need to show any of them to the
    # user
    return fields


def send_email_verification_email(request, user, email):
    token_service = request.find_service(ITokenService, name="email")

    token = token_service.dumps({"action": "email-verify", "email.id": email.id})

    fields = {
        "token": token,
        "email_address": email.email,
        "n_hours": token_service.max_age // 60 // 60,
    }

    msg = EmailMessage.from_template("verify-email", fields, request=request)

    _send_email_to_user(request, user, msg, email=email, allow_unverified=True)

    return fields


def send_password_change_email(request, user):
    fields = {"username": user.username}
    msg = EmailMessage.from_template("password-change", fields, request=request)

    _send_email_to_user(request, user, msg)

    return fields


def send_account_deletion_email(request, user):
    fields = {"username": user.username}
    msg = EmailMessage.from_template("account-deleted", fields, request=request)

    _send_email_to_user(request, user, msg)

    return fields


def send_primary_email_change_email(request, user, email):
    fields = {
        "username": user.username,
        "old_email": email.email,
        "new_email": user.email,
    }

    msg = EmailMessage.from_template("primary-email-change", fields, request=request)

    _send_email_to_user(request, user, msg, email=email)

    return fields


def send_collaborator_added_email(
    request, user, submitter, project_name, role, email_recipients
):
    fields = {
        "username": user.username,
        "project": project_name,
        "submitter": submitter.username,
        "role": role,
    }

    msg = EmailMessage.from_template("collaborator-added", fields, request=request)

    for recipient in email_recipients:
        _send_email_to_user(request, recipient, msg)

    return fields


def send_added_as_collaborator_email(request, submitter, project_name, role, user):
    fields = {"project": project_name, "submitter": submitter.username, "role": role}
    msg = EmailMessage.from_template("added-as-collaborator", fields, request=request)

    _send_email_to_user(request, user, msg)

    return fields


def includeme(config):
    email_sending_class = config.maybe_dotted(config.registry.settings["mail.backend"])
    config.register_service_factory(email_sending_class.create_service, IEmailSender)

    # Add a periodic task to cleanup our EmailMessage table. We're going to
    # do this cleanup, regardless of if we're configured to use SES to send
    # or not, because even if we stop using SES, we'll want to remove any
    # emails that had been sent, and the cost of doing this is very low.
    config.add_periodic_task(crontab(minute=0, hour=0), ses_cleanup)
