from warehouse.conf import Settings


class Common(Settings):

    # Do NOT use this in production or anywhere this is exposed to the public
    SECRET_KEY = "insecure testing secret key"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
        }
    }


class Development(Common):

    DEBUG = True
    TEMPLATE_DEBUG = True


class Production(Common):
    pass
