# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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

        # Create the config file
        with open(path, "w", encoding="utf-8") as configfile:
            configfile.write("""# Warehouse settings
from warehouse.conf import Settings


class Common(Settings):
    \"\"\"
    Common settings for this Warehouse instance.
    \"\"\"

    SECRET_KEY = "{secret_key}"


class Development(Common):
    \"\"\"
    Development settings for this Warehouse instance.
    \"\"\"

    DEBUG = True
    TEMPLATE_DEBUG = True


class Production(Common):
    \"\"\"
    Production settings for this Warehouse instance.
    \"\"\"
""".format(secret_key=secret_key))
