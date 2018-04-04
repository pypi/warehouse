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

from pyramid.renderers import render

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import SMTPEmailSender


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def send_email(task, request, subject, body, *, recipient=None):
    sender = request.find_service(IEmailSender)

    try:
        sender.send(subject, body, recipient=recipient)
    except Exception as exc:
        task.retry(exc=exc)


def send_password_reset_email(request, user):
    token_service = request.find_service(ITokenService, name='password')
    token = token_service.dumps({
        'action': 'password-reset',
        'user.id': str(user.id),
        'user.last_login': str(user.last_login),
        'user.password_date': str(user.password_date),
    })

    fields = {
        'token': token,
        'username': user.username,
        'n_hours': token_service.max_age // 60 // 60,
    }

    subject = render(
        'email/password-reset.subject.txt', fields, request=request
    )

    body = render(
        'email/password-reset.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=user.email)

    # Return the fields we used, in case we need to show any of them to the
    # user
    return fields


def send_email_verification_email(request, email):
    token_service = request.find_service(ITokenService, name='email')

    token = token_service.dumps({
        "action": "email-verify",
        "email.id": email.id,
    })

    fields = {
        'token': token,
        'email_address': email.email,
        'n_hours': token_service.max_age // 60 // 60,
    }

    subject = render(
        'email/verify-email.subject.txt', fields, request=request
    )

    body = render(
        'email/verify-email.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=email.email)

    return fields


def send_password_change_email(request, user):
    fields = {
        'username': user.username,
    }

    subject = render(
        'email/password-change.subject.txt', fields, request=request
    )

    body = render(
        'email/password-change.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=user.email)

    return fields


def send_account_deletion_email(request, user):
    fields = {
        'username': user.username,
    }

    subject = render(
        'email/account-deleted.subject.txt', fields, request=request
    )

    body = render(
        'email/account-deleted.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=user.email)

    return fields


def send_primary_email_change_email(request, user, email):
    fields = {
        'username': user.username,
        'old_email': email,
        'new_email': user.email,
    }

    subject = render(
        'email/primary-email-change.subject.txt', fields, request=request
    )

    body = render(
        'email/primary-email-change.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=email)

    return fields


def send_collaborator_added_email(request, user, submitter, project_name, role,
                                  email_recipients):
    fields = {
        'username': user.username,
        'project': project_name,
        'submitter': submitter.username,
        'role': role
    }

    subject = render(
        'email/collaborator-added.subject.txt', fields, request=request
    )

    body = render(
        'email/collaborator-added.body.txt', fields, request=request
    )

    for recipient in email_recipients:
        request.task(send_email).delay(subject, body, recipient=recipient)

    return fields


def send_added_as_collaborator_email(request, submitter, project_name, role,
                                     user_email):
    fields = {
        'project': project_name,
        'submitter': submitter.username,
        'role': role
    }

    subject = render(
        'email/added-as-collaborator.subject.txt', fields, request=request
    )

    body = render(
        'email/added-as-collaborator.body.txt', fields, request=request
    )

    request.task(send_email).delay(subject, body, recipient=user_email)

    return fields


def includeme(config):
    config.register_service_factory(
        SMTPEmailSender.create_service,
        IEmailSender,
    )
