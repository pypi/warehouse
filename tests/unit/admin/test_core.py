# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from warehouse import admin
from warehouse.admin.services import LocalSponsorLogoStorage


def test_includeme(mock_manifest_cache_buster, monkeypatch, mocker):
    storage_class = mocker.create_autospec(LocalSponsorLogoStorage)
    monkeypatch.setattr(admin, "ManifestCacheBuster", mock_manifest_cache_buster)
    config = mocker.Mock(
        spec=[
            "get_settings",
            "registry",
            "add_cache_buster",
            "whitenoise_add_files",
            "whitenoise_add_manifest",
            "add_jinja2_search_path",
            "add_static_view",
            "include",
            "maybe_dotted",
            "register_service_factory",
        ]
    )
    config.get_settings.return_value = {}
    config.registry = SimpleNamespace(
        settings={
            "pyramid.reload_assets": False,
            "sponsorlogos.backend": "warehouse.admin.services.LocalSponsorLogoStorage",
        }
    )
    config.maybe_dotted.return_value = storage_class

    admin.includeme(config)

    config.whitenoise_add_files.assert_called_once_with(
        "warehouse.admin:static/dist/", prefix="/admin/static/"
    )
    config.whitenoise_add_manifest.assert_called_once_with(
        "warehouse.admin:static/dist/manifest.json", prefix="/admin/static/"
    )
    config.add_jinja2_search_path.assert_called_once_with("templates", name=".html")
    config.add_static_view.assert_called_once_with(
        "admin/static", "warehouse.admin:static/dist", cache_max_age=315360000
    )
    assert config.include.call_args_list == [
        mocker.call("pyramid_components"),
        mocker.call(".routes"),
        mocker.call(".flags"),
        mocker.call(".bans"),
    ]

    config.maybe_dotted.assert_called_once_with(
        "warehouse.admin.services.LocalSponsorLogoStorage"
    )
    config.register_service_factory.assert_called_once_with(
        storage_class.create_service, admin.interfaces.ISponsorLogoStorage
    )
    storage_class.create_service.assert_not_called()
