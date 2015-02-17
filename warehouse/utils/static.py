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

from pyramid.path import AssetResolver


class WarehouseCacheBuster:

    def __init__(self, manifest, cache=True):
        self.manifest_asset = manifest
        self.cache = cache

    def _load_manifest(self):
        manifest = getattr(self, "_manifest", None)

        if manifest is None:
            manifest = AssetResolver().resolve(self.manifest_asset)
            with manifest.stream() as fp:
                manifest = json.loads(fp.read().decode("utf8"))

            if self.cache:
                self._manifest = manifest

        return manifest

    def token(self, pathspec):
        """
        Our cache buster doesn't generate it's own tokens, instead it just
        looks the asset up in a dictionary and reads that.
        """

    def pregenerate(self, token, subpath, kw):
        path = "/".join(subpath)

        # Attempt to look our path up in our manifest file, if it does not
        # exist then we'll just return the original path.
        manifest = self._load_manifest()
        path = manifest.get(path, path)

        return tuple(path.split("/")), kw

    def match(self, subpath):
        path = "/".join(subpath)

        # Attempt to look our path up in our manifest file, if it does not
        # exist then we'll just return the original path.
        manifest = {v: k for k, v in self._load_manifest().items()}
        path = manifest.get(path, path)

        return tuple(path.split("/"))
