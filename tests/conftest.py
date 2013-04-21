import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        path, name = item.nodeid.split("::")
        if path.startswith("tests/unit/"):
            item.keywords["unit"] = pytest.mark.unit
        elif path.startswith("tests/functional"):
            item.keywords["functional"] = pytest.mark.functional


@pytest.fixture
def webtest(request):
    from django.conf import settings
    from django.test.utils import override_settings

    from django_webtest import DjangoTestApp

    middleware = list(settings.MIDDLEWARE_CLASSES)
    django_auth_middleware = ("django.contrib.auth.middleware."
                                                    "AuthenticationMiddleware")
    webtest_auth_middleware = "django_webtest.middleware.WebtestUserMiddleware"
    if django_auth_middleware not in settings.MIDDLEWARE_CLASSES:
        # There can be a custom AuthenticationMiddleware subclass or
        #   replacement, we can't compute its index so just put our auth
        #   middleware to the end.
        middleware.append(webtest_auth_middleware)
    else:
        index = middleware.index(django_auth_middleware)
        middleware.insert(index+1, webtest_auth_middleware)

    auth_backends = ["django_webtest.backends.WebtestUserBackend"]
    auth_backends += list(settings.AUTHENTICATION_BACKENDS)

    patched_settings = override_settings(
                            # We want exceptions to be raised naturally so that
                            #   they are treated like normal exceptions in a
                            #   test case.
                            DEBUG_PROPAGATE_EXCEPTIONS=True,
                            # We want to insert the django-webtest middleware
                            #   into our middleware classes so that we can
                            #   auth from a webtest easily.
                            MIDDLEWARE_CLASSES=middleware,
                            # We want to insert the django-webtest
                            #   authentication backend so that webtest can
                            #   easily authenticate.
                            AUTHENTICATION_BACKENDS=auth_backends,
                        )
    patched_settings.enable()
    request.addfinalizer(patched_settings.disable)

    return DjangoTestApp()
