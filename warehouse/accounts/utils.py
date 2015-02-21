from email.mime.text import MIMEText

FROM_EMAIL = 'warehouse@python.org'

EMAIL_BODY = """
Hi {email_address},

thanks for registering for Warehouse! Please confirm your email
address by navigating to the url below:

{confirmation_link}
"""


def get_confirmation_email(email_address, confirmation_link):
    """
    given a confirmation_code,
    generate the body of a confirmation email
    """

    body = EMAIL_BODY.format(email_address=email_address,
                             confirmation_link=confirmation_link)
    msg = MIMEText(body)
    msg['Subject'] = "Please confirm your Warehouse account"
    msg['From'] = FROM_EMAIL
    msg['To'] = email_address
    return msg
