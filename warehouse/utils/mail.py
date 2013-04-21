from django.core.mail import EmailMessage


def send_mail(recipients, subject, message, from_address=None,
                                                message_class=EmailMessage):
    return message_class(subject, message, from_address, recipients).send()
