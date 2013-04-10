from warehouse.conf import Settings


class Common(Settings):

    SITE_NAME = "Warehouse (Dev)"

    # Do NOT use this in production or anywhere this is exposed to the public
    SECRET_KEY = "insecure development secret key"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
            "NAME": "warehouse",
        }
    }


class Development(Common):

    DEBUG = True
    TEMPLATE_DEBUG = True


class Production(Common):
    pass
