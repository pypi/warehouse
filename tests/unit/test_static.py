# SPDX-License-Identifier: Apache-2.0

import types

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
    def test_no_config(self, pyramid_config, mocker):
        app = mocker.sentinel.app
        assert static._create_whitenoise(app, pyramid_config) is app

    def test_creates(self, pyramid_config, mocker):
        app = mocker.sentinel.app
        pyramid_config.registry.settings.update(
            {
                "whitenoise": {"autorefresh": False},
                "whitenoise.files": [("/foo/", {"prefix": "/static/"})],
                "whitenoise.manifests": [("/manifest.json", "/static/")],
            }
        )

        file_test_cls = mocker.patch.object(
            static, "ImmutableManifestFiles", autospec=True
        )
        whitenoise_cls = mocker.patch.object(static, "WhiteNoise", autospec=True)

        static._create_whitenoise(app, pyramid_config)

        whitenoise_cls.assert_called_once_with(
            app, autorefresh=False, immutable_file_test=file_test_cls.return_value
        )
        whitenoise_cls.return_value.add_files.assert_called_once_with(
            "/foo", prefix="/static/"
        )
        file_test_cls.assert_called_once_with()
        file_test_cls.return_value.add_manifest.assert_called_once_with(
            "/manifest.json", "/static/"
        )

    def test_whitenoise_serve_static(self, mocker):
        config = mocker.Mock(spec=["action", "registry"])
        config.registry = types.SimpleNamespace(settings={})
        config.action.side_effect = lambda token, callback: callback()
        kwargs = {"foo": "bar"}

        static.whitenoise_serve_static(config, **kwargs)

        assert config.registry.settings["whitenoise"] == kwargs
        assert config.action.call_count == 1

    def test_whitenoise_add_files(self, mocker):
        config = mocker.Mock(spec=["action", "registry"])
        config.registry = types.SimpleNamespace(settings={})
        config.action.side_effect = lambda token, callback: callback()
        path = mocker.sentinel.path
        prefix = mocker.sentinel.prefix

        static.whitenoise_add_files(config, path, prefix)

        assert config.registry.settings["whitenoise.files"] == [
            (path, {"prefix": prefix})
        ]
        assert config.action.call_count == 1

    def test_whitenoise_add_manifest(self, mocker):
        config = mocker.Mock(spec=["action", "registry"])
        config.registry = types.SimpleNamespace(settings={})
        config.action.side_effect = lambda token, callback: callback()
        manifest = mocker.sentinel.manifest
        prefix = mocker.sentinel.prefix

        static.whitenoise_add_manifest(config, manifest, prefix)

        assert config.registry.settings["whitenoise.manifests"] == [(manifest, prefix)]
        assert config.action.call_count == 1


def test_includeme(mocker):
    config = mocker.Mock(spec=["add_wsgi_middleware", "add_directive"])

    static.includeme(config)

    config.add_wsgi_middleware.assert_called_once_with(
        static._create_whitenoise, config
    )
    assert config.add_directive.call_args_list == [
        mocker.call("whitenoise_serve_static", static.whitenoise_serve_static),
        mocker.call("whitenoise_add_files", static.whitenoise_add_files),
        mocker.call("whitenoise_add_manifest", static.whitenoise_add_manifest),
    ]
