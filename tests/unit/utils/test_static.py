# SPDX-License-Identifier: Apache-2.0

from warehouse.utils.static import ManifestCacheBuster


class TestManifestCacheBuster:
    def test_returns_when_valid(self, monkeypatch):
        monkeypatch.setattr(
            ManifestCacheBuster,
            "get_manifest",
            lambda x: {"/the/path/style.css": "/the/busted/path/style.css"},
        )
        cb = ManifestCacheBuster("warehouse:static/dist/manifest.json")
        result = cb(None, "/the/path/style.css", {"keyword": "arg"})

        assert result == ("/the/busted/path/style.css", {"keyword": "arg"})

    def test_passes_when_invalid(self, monkeypatch):
        monkeypatch.setattr(ManifestCacheBuster, "get_manifest", lambda x: {})
        cb = ManifestCacheBuster("warehouse:static/dist/manifest.json")

        cb(None, "/the/path/style.css", {"keyword": "arg"})

    def test_returns_when_invalid_and_not_strict(self, monkeypatch):
        monkeypatch.setattr(ManifestCacheBuster, "get_manifest", lambda x: {})
        cb = ManifestCacheBuster("warehouse:static/dist/manifest.json", strict=False)
        result = cb(None, "/the/path/style.css", {"keyword": "arg"})

        assert result == ("/the/path/style.css", {"keyword": "arg"})
