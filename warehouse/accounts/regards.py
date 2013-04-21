from django.conf import settings
from django.template.loader import render_to_string

from warehouse.accounts.models import Email, User
from warehouse.utils.mail import send_mail


class UserCreator(object):

    user_creator = User.api.create
    email_creator = Email.api.create
    mailer = send_mail

    def __init__(self, user_creator=None, email_creator=None, mailer=None):
        if user_creator is not None:
            self.user_creator = user_creator

        if email_creator is not None:
            self.email_creator = email_creator

        if mailer is not None:
            self.mailer = mailer

    def __call__(self, username, email, password):
        # Create the User in the Database
        user = self.user_creator(username, password)

        # Associate the Email address with the User
        user_email = self.email_creator(user.username, email)

        # Send an Email to the User
        subject = render_to_string("accounts/emails/welcome_subject.txt", {
                        "user": user,
                        "SITE_NAME": settings.SITE_NAME,
                    }).strip()
        body = render_to_string("accounts/emails/welcome_body.txt", {
                        "user": user,
                        "SITE_NAME": settings.SITE_NAME,
                    }).strip()
        send_mail([user_email.email], subject, body)

        # Return the User
        return user
