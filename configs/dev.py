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

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
        }
    }


class Production(Common):
    pass
