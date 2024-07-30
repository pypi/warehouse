# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
