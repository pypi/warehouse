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

from warehouse import static


class TestImmutableManifestFiles:
    def test_returns_nothing_when_no_manifests(self):
        manifest = static.ImmutableManifestFiles()
        assert not manifest("/foo/static/bar.css", "/static/bar.css")

    def test_file_not_in_manifest_dir(self, tmpdir):
        with open(str(tmpdir.join("manifest.json")), "w") as fp:
            fp.write("{}")

        manifest = static.ImmutableManifestFiles()
        manifest.add_manifest(str(tmpdir.join("manifest.json")), "/static/")

        assert not manifest("/foo/static/bar.css", "/static/bar.css")

    def test_file_not_in_manifest(self, tmpdir):
        with open(str(tmpdir.join("manifest.json")), "w") as fp:
            fp.write('{"css/bar.css": "css/bar.hash.css"}')

        manifest = static.ImmutableManifestFiles()
        manifest.add_manifest(str(tmpdir.join("manifest.json")), "/static/")

        assert not manifest(
            str(tmpdir.join("css/foo.hash.css")), "/static/foo.hash.css"
        )

    def test_file_in_manifest(self, tmpdir):
        with open(str(tmpdir.join("manifest.json")), "w") as fp:
            fp.write('{"css/bar.css": "css/bar.hash.css"}')

        manifest = static.ImmutableManifestFiles()
        manifest.add_manifest(str(tmpdir.join("manifest.json")), "/static/")

        assert manifest(str(tmpdir.join("css/bar.hash.css")), "/static/bar.hash.css")

    def test_file_wrong_prefix(self, tmpdir):
        with open(str(tmpdir.join("manifest.json")), "w") as fp:
            fp.write('{"css/bar.css": "css/bar.hash.css"}')

        manifest = static.ImmutableManifestFiles()
        manifest.add_manifest(str(tmpdir.join("manifest.json")), "/static/")

        assert not manifest(str(tmpdir.join("css/bar.hash.css")), "/other/bar.hash.css")


class TestCreateWhitenoise:
    def test_no_config(self):
        app = pretend.stub()
        config = pretend.stub(registry=pretend.stub(settings={}))
        assert static._create_whitenoise(app, config) is app

    def test_creates(self, monkeypatch):
        app = pretend.stub()
        config = pretend.stub(
            registry=pretend.stub(
                settings={
                    "whitenoise": {"autorefresh": False},
                    "whitenoise.files": [("/foo/", {"prefix": "/static/"})],
                    "whitenoise.manifests": [("/manifest.json", "/static/")],
                }
            )
        )

        file_test_obj = pretend.stub(
            add_manifest=pretend.call_recorder(lambda *a, **kw: None)
        )
        file_test_cls = pretend.call_recorder(lambda: file_test_obj)
        monkeypatch.setattr(static, "ImmutableManifestFiles", file_test_cls)

        whitenoise_obj = pretend.stub(
            add_files=pretend.call_recorder(lambda path, prefix: None)
        )
        whitenoise_cls = pretend.call_recorder(lambda app, **kw: whitenoise_obj)
        monkeypatch.setattr(static, "WhiteNoise", whitenoise_cls)

        static._create_whitenoise(app, config)

        assert whitenoise_cls.calls == [
            pretend.call(app, autorefresh=False, immutable_file_test=file_test_obj)
        ]
        assert whitenoise_obj.add_files.calls == [
            pretend.call("/foo", prefix="/static/")
        ]
        assert file_test_cls.calls == [pretend.call()]
        assert file_test_obj.add_manifest.calls == [
            pretend.call("/manifest.json", "/static/")
        ]

    def test_whitenoise_serve_static(self):
        config = pretend.stub(
            action=pretend.call_recorder(lambda t, f: f()),
            registry=pretend.stub(settings={}),
        )
        kwargs = {"foo": "bar"}

        static.whitenoise_serve_static(config, **kwargs)

        assert config.registry.settings["whitenoise"] == kwargs
        assert len(config.action.calls) == 1

    def test_whitenoise_add_files(self):
        config = pretend.stub(
            action=pretend.call_recorder(lambda t, f: f()),
            registry=pretend.stub(settings={}),
        )
        path = pretend.stub()
        prefix = pretend.stub()

        static.whitenoise_add_files(config, path, prefix)

        assert config.registry.settings["whitenoise.files"] == [
            (path, {"prefix": prefix})
        ]
        assert len(config.action.calls) == 1

    def test_whitenoise_add_manifest(self):
        config = pretend.stub(
            action=pretend.call_recorder(lambda t, f: f()),
            registry=pretend.stub(settings={}),
        )
        manifest = pretend.stub()
        prefix = pretend.stub()

        static.whitenoise_add_manifest(config, manifest, prefix)

        assert config.registry.settings["whitenoise.manifests"] == [(manifest, prefix)]
        assert len(config.action.calls) == 1


def test_includeme():
    config = pretend.stub(
        add_wsgi_middleware=pretend.call_recorder(lambda *a, **kw: None),
        add_directive=pretend.call_recorder(lambda name, callable: None),
    )

    static.includeme(config)

    assert config.add_wsgi_middleware.calls == [
        pretend.call(static._create_whitenoise, config)
    ]
    assert config.add_directive.calls == [
        pretend.call("whitenoise_serve_static", static.whitenoise_serve_static),
        pretend.call("whitenoise_add_files", static.whitenoise_add_files),
        pretend.call("whitenoise_add_manifest", static.whitenoise_add_manifest),
    ]
