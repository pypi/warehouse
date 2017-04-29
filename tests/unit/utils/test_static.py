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

import pytest

from warehouse.utils.static import ManifestCacheBuster


class TestManifestCacheBuster(object):

    def test_returns_when_valid(self):
        cb = ManifestCacheBuster("warehouse:static/dist/manifest.json")
        cb._manifest = {"/the/path/style.css": "/the/busted/path/style.css"}
        result = cb(None, "/the/path/style.css", {"keyword": "arg"})

        assert result == ("/the/busted/path/style.css", {"keyword": "arg"})

    def test_raises_when_invalid(self):
        cb = ManifestCacheBuster("warehouse:static/dist/manifest.json")
        cb._manifest = {}

        with pytest.raises(ValueError):
            cb(None, "/the/path/style.css", {"keyword": "arg"})

    def test_returns_when_invalid_and_not_strict(self):
        cb = ManifestCacheBuster(
            "warehouse:static/dist/manifest.json",
            strict=False,
        )
        cb._manifest = {}
        result = cb(None, "/the/path/style.css", {"keyword": "arg"})

        assert result == ("/the/path/style.css", {"keyword": "arg"})
