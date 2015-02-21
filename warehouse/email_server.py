import logging
import smtplib

logger = logging.getLogger(__name__)


class EmailServer:
    """
    A class that handles sending email

    it wraps smtplib to allow for cases in which sending email is not
    desired
    """

    def __init__(self, config, email_class=smtplib.SMTP):
        self.is_disabled = config.get("disabled", False)
        if not self.is_disabled:
            self._smtp_server = email_class(config["url"])

    def send_message(self, body):
        if self.is_disabled:
            logger.warn("email is disabled. a message was "
                        "attempted to be sent, but will be ignored")
            logger.debug("email body: " + str(body))
        else:
            self._smtp_server.send_message(body)
