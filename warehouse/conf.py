"""
Default settings for warehouse.
"""
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
