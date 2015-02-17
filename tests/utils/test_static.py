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

import pretend

from warehouse.utils import static


class TestWarehouseCacheBuster:

    def test_accepts_manifest_asset(self):
        cachebuster = static.WarehouseCacheBuster("foo")
        assert cachebuster.manifest_asset == "foo"

    def test_load_manifest(self, monkeypatch):
        class FakeStream:
            def __enter__(self):
                return self

            def __exit__(self, *args, **kwargs):
                pass

            def read(self):
                return b'{"css/style.css": "css/style-foo.css"}'

        class FakeAsset:
            def stream(self):
                return FakeStream()

        assetresolver_obj = pretend.stub(resolve=lambda spec: FakeAsset())
        monkeypatch.setattr(static, "AssetResolver", lambda: assetresolver_obj)

        cachebuster = static.WarehouseCacheBuster("foo")
        manifest = cachebuster._load_manifest()

        assert manifest == {"css/style.css": "css/style-foo.css"}

    def test_token(self):
        cachebuster = static.WarehouseCacheBuster("no-op")
        assert cachebuster.token(None) is None

    def test_pregenerate(self):
        def load_manifest():
            return {"css/style.css": "css/style-pre.css"}

        cachebuster = static.WarehouseCacheBuster("pregenerate")
        cachebuster._load_manifest = load_manifest

        r = cachebuster.pregenerate(None, ("css", "style.css"), {"foo": "bar"})
        assert r == (("css", "style-pre.css"), {"foo": "bar"})

    def test_match(self):
        def load_manifest():
            return {"css/style.css": "css/style-match.css"}

        cachebuster = static.WarehouseCacheBuster("match")
        cachebuster._load_manifest = load_manifest

        r = cachebuster.match(("css", "style-match.css"))
        assert r == ("css", "style.css")
