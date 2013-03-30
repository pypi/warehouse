import os

from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string


class Command(BaseCommand):
    args = "<path>"

    def handle(self, *args, **options):
        if not args:
            raise CommandError("You must provide a config path")
        if len(args) > 1:
            raise CommandError("Only one config path may be initialized")

        # Create an absolute path
        path = os.path.abspath(args[0])

        # Create a random SECRET_KEY hash to put it in the main settings.
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        secret_key = get_random_string(50, chars)

        # Create the config.yaml file
        with open(path, "w", encoding="utf-8") as configfile:
            configfile.write("""# Warehouse settings
COMMON: &common
    SECRET_KEY: "{secret_key}"

DEVELOPMENT: &development
    <<: *common

    DEBUG: true
    TEMPLATE_DEBUG: true

PRODUCTION: &production
    <<: *common
""".format(secret_key=secret_key))
