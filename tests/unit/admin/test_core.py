# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import admin


def test_includeme(mock_manifest_cache_buster, monkeypatch):
    storage_class = pretend.stub(
        create_service=pretend.call_recorder(lambda *a, **kw: pretend.stub())
    )
    monkeypatch.setattr(admin, "ManifestCacheBuster", mock_manifest_cache_buster)
    _sponsorlogos_backend = "warehouse.admin.services.LocalSponsorLogoStorage"
    config = pretend.stub(
        get_settings=lambda: {},
        registry=pretend.stub(
            settings={
                "pyramid.reload_assets": False,
                "sponsorlogos.backend": _sponsorlogos_backend,
            }
        ),
        add_cache_buster=pretend.call_recorder(lambda *a, **kw: None),
        whitenoise_add_files=pretend.call_recorder(lambda *a, **kw: None),
        whitenoise_add_manifest=pretend.call_recorder(lambda *a, **kw: None),
        add_jinja2_search_path=pretend.call_recorder(lambda path, name: None),
        add_static_view=pretend.call_recorder(lambda name, path, cache_max_age: None),
        include=pretend.call_recorder(lambda name: None),
        add_view=pretend.call_recorder(lambda *a, **kw: None),
        maybe_dotted=pretend.call_recorder(lambda dotted: storage_class),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
    )

    admin.includeme(config)

    assert config.whitenoise_add_files.calls == [
        pretend.call("warehouse.admin:static/dist/", prefix="/admin/static/")
    ]
    assert config.whitenoise_add_manifest.calls == [
        pretend.call(
            "warehouse.admin:static/dist/manifest.json", prefix="/admin/static/"
        )
    ]
    assert config.add_jinja2_search_path.calls == [
        pretend.call("templates", name=".html")
    ]
    assert config.add_static_view.calls == [
        pretend.call(
            "admin/static", "warehouse.admin:static/dist", cache_max_age=315360000
        )
    ]
    assert config.include.calls == [
        pretend.call(".routes"),
        pretend.call(".flags"),
        pretend.call(".bans"),
    ]

    assert config.maybe_dotted.calls == [
        pretend.call("warehouse.admin.services.LocalSponsorLogoStorage")
    ]
    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, admin.interfaces.ISponsorLogoStorage)
    ]
    assert storage_class.create_service.calls == []
