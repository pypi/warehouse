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
import pytest

from warehouse.utils import static


class TestWarehouseCacheBuster:

    def test_accepts_manifest_asset(self):
        cachebuster = static.WarehouseCacheBuster("foo")
        assert cachebuster.manifest_asset == "foo"

    @pytest.mark.parametrize("cache", [True, False])
    def test_load_manifest(self, monkeypatch, cache):
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
        assetresolver_cls = pretend.call_recorder(lambda: assetresolver_obj)
        monkeypatch.setattr(static, "AssetResolver", assetresolver_cls)

        cachebuster = static.WarehouseCacheBuster("foo", cache=cache)
        manifest = cachebuster._load_manifest()
        manifest = cachebuster._load_manifest()

        assert manifest == {"css/style.css": "css/style-foo.css"}

        if cache:
            assert assetresolver_cls.calls == [pretend.call()]
        else:
            assert assetresolver_cls.calls == [pretend.call(), pretend.call()]

    def test_pregenerate(self):
        def load_manifest():
            return {"css/style.css": "css/style-pre.css"}

        cachebuster = static.WarehouseCacheBuster("pregenerate")
        cachebuster._load_manifest = load_manifest

        r = cachebuster.pregenerate(None, ("css", "style.css"), {"foo": "bar"})
        assert r == (("css", "style-pre.css"), {"foo": "bar"})
