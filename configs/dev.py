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
from warehouse.conf import Settings


class Common(Settings):

    # Do NOT use this in production or anywhere this is exposed to the public
    SECRET_KEY = "insecure secret key"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            "NAME": "warehouse",
        }
    }


class Development(Common):

    SITE_NAME = "Warehouse (Dev)"

    DEBUG = True
    TEMPLATE_DEBUG = True

    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


class Testing(Common):
    pass


class Production(Common):
    pass
