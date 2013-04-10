from django.test.utils import override_settings

from warehouse.context_processors import site_name


@override_settings(SITE_NAME="Warehouse (Test)")
def test_site_name(rf):
    request = rf.get("/")
    assert site_name(request) == {"SITE_NAME": "Warehouse (Test)"}
