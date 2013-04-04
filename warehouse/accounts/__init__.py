from django.utils.translation import ugettext_lazy as _

VALID_USERNAME_REGEX = r"^[\w.-]+$"
VALID_USERNAME_DESC = _(
                    "50 characters or fewer. Letters, digits, and ./-/_ only.")
INVALID_USERNAME_MSG = _(
        "This value may contain only letters, numbers, and ./-/_ characters.")
