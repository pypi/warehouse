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

import json
import os.path

from pyramid.path import AssetResolver
from whitenoise import WhiteNoise

resolver = AssetResolver()


class ImmutableManifestFiles:
    def __init__(self):
        self.manifests = {}

    def __call__(self, path, url):
        manifest_path, manifest = self.get_manifest(url)
        if manifest_path is not None:
            manifest_dir = os.path.dirname(manifest_path)
            if os.path.commonpath([manifest_path, path]) == manifest_dir:
                if os.path.relpath(path, manifest_dir) in manifest:
                    return True

        return False

    def add_manifest(self, manifest_path, prefix):
        self.manifests[prefix] = resolver.resolve(manifest_path).abspath()

    def get_manifest(self, url):
        for prefix, manifest_path in self.manifests.items():
            if url.startswith(prefix):
                manifest_files = set()

                with open(manifest_path, "r", encoding="utf8") as fp:
                    data = json.load(fp)
                manifest_files.update(data.values())

                return manifest_path, manifest_files

        return None, None


def _create_whitenoise(app, config):
    wh_config = config.registry.settings.get("whitenoise", {}).copy()
    if wh_config:
        # Create our Manifest immutable file checker.
        manifest = ImmutableManifestFiles()
        for manifest_spec, prefix in config.registry.settings.get(
            "whitenoise.manifests", []
        ):
            manifest.add_manifest(manifest_spec, prefix)

        # Wrap our WSGI application with WhiteNoise
        app = WhiteNoise(app, **wh_config, immutable_file_test=manifest)

        # Go through and add all of the files we were meant to add.
        for path, kwargs in config.registry.settings.get("whitenoise.files", []):
            app.add_files(resolver.resolve(path).abspath(), **kwargs)

    return app


def whitenoise_serve_static(config, **kwargs):
    def register():
        config.registry.settings["whitenoise"] = kwargs

    config.action(("whitenoise", "create instance"), register)


def whitenoise_add_files(config, path, prefix=None):
    def add_files():
        config.registry.settings.setdefault("whitenoise.files", []).append(
            (path, {"prefix": prefix})
        )

    config.action(("whitenoise", "add files", path, prefix), add_files)


def whitenoise_add_manifest(config, manifest, prefix):
    def add_manifest():
        config.registry.settings.setdefault("whitenoise.manifests", []).append(
            (manifest, prefix)
        )

    config.action(("whitenoise", "add manifest", manifest), add_manifest)


def includeme(config):
    config.add_wsgi_middleware(_create_whitenoise, config)
    config.add_directive("whitenoise_serve_static", whitenoise_serve_static)
    config.add_directive("whitenoise_add_files", whitenoise_add_files)
    config.add_directive("whitenoise_add_manifest", whitenoise_add_manifest)
