from django.conf import settings


def site_name(request):
    return {"SITE_NAME": settings.SITE_NAME}
