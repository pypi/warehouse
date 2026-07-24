# SPDX-License-Identifier: Apache-2.0

from warehouse.admin.services import ISponsorLogoStorage
from warehouse.utils.static import ManifestCacheBuster


def includeme(config):
    sponsorlogos_storage_class = config.maybe_dotted(
        config.registry.settings["sponsorlogos.backend"]
    )
    config.register_service_factory(
        sponsorlogos_storage_class.create_service, ISponsorLogoStorage
    )

    # Setup Jinja2 Rendering for the Admin application
    config.add_jinja2_search_path("templates", name=".html")

    # Register the {% component %} tag, then import the component modules so
    # they register themselves. Component templates are asset specs
    # (warehouse.admin:components/...), so no search path is needed.
    config.include("pyramid_components")
    # Imported here (not at module top) to avoid an import-time side effect on
    # the module.
    from warehouse.admin import components  # noqa: F401, PLC0415

    # Setup our static assets
    prevent_http_cache = config.get_settings().get("pyramid.prevent_http_cache", False)
    config.add_static_view(
        "admin/static",
        "warehouse.admin:static/dist",
        # Don't cache at all if prevent_http_cache is true, else we'll cache
        # the files for 10 years.
        cache_max_age=0 if prevent_http_cache else 10 * 365 * 24 * 60 * 60,
    )
    config.add_cache_buster(
        "warehouse.admin:static/dist/",
        ManifestCacheBuster(
            "warehouse.admin:static/dist/manifest.json",
            reload=config.registry.settings["pyramid.reload_assets"],
            strict=not prevent_http_cache,
        ),
    )
    config.whitenoise_add_files("warehouse.admin:static/dist/", prefix="/admin/static/")
    config.whitenoise_add_manifest(
        "warehouse.admin:static/dist/manifest.json", prefix="/admin/static/"
    )

    # Add our routes
    config.include(".routes")

    # Add our flags
    config.include(".flags")

    # Add our bans
    config.include(".bans")
