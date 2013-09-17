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
from configurations import Settings as BaseSettings


class Settings(BaseSettings):
    INSTALLED_APPS = [
        # Django Contrib Apps
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",

        # External Applications
        "south",

        # Warehouse Apps
        "warehouse",
        "warehouse.accounts",
        "warehouse.utils",
    ]

    AUTH_USER_MODEL = "accounts.User"

    MIDDLEWARE_CLASSES = [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]

    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
        "django.contrib.auth.hashers.BCryptPasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]

    ROOT_URLCONF = "warehouse.urls"

    WSGI_APPLICATION = "warehouse.wsgi.application"

    LANGUAGE_CODE = "en"

    TIME_ZONE = "UTC"

    USE_I18N = True
    USE_L10N = True

    USE_TZ = True

    STATIC_URL = "/static/"

    TEMPLATE_CONTEXT_PROCESSORS = [
        "django.contrib.auth.context_processors.auth",
        "django.core.context_processors.debug",
        "django.core.context_processors.i18n",
        "django.core.context_processors.media",
        "django.core.context_processors.static",
        "django.core.context_processors.tz",
        "django.contrib.messages.context_processors.messages",
        "warehouse.context_processors.site_name",
    ]

    SITE_NAME = "Warehouse"

    LOGIN_URL = "accounts.login"
    LOGIN_REDIRECT_URL = "accounts.settings"
