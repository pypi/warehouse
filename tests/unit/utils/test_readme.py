# SPDX-License-Identifier: Apache-2.0

from importlib.metadata import PackageNotFoundError

import pretend
import pytest

from warehouse.utils import readme


@pytest.fixture(autouse=True)
def _clear_renderer_version_cache():
    readme.renderer_version.cache_clear()
    yield
    readme.renderer_version.cache_clear()


@pytest.fixture
def fake_distributions(monkeypatch):
    def _fake_distributions(versions):
        def _distribution(name):
            try:
                version = versions[name]
            except KeyError:
                raise PackageNotFoundError(name)
            return pretend.stub(version=version)

        monkeypatch.setattr(readme, "distribution", _distribution)

    return _fake_distributions


def test_render_with_none():
    result = readme.render(None)
    assert result is None


def test_can_render_rst():
    result = readme.render("raw thing", "text/x-rst")
    assert result == "<p>raw thing</p>\n"


def test_cant_render_rst():
    result = readme.render("raw `<thing", "text/x-rst")
    assert result == "raw `&lt;thing"


def test_can_render_plaintext():
    result = readme.render("raw thing", "text/plain")
    assert result == "<pre>raw thing</pre>"


def test_can_render_markdown():
    result = readme.render("raw thing", "text/markdown")
    assert result == "<p>raw thing</p>\n"


def test_can_render_missing_content_type():
    result = readme.render("raw thing")
    assert result == "<p>raw thing</p>\n"


def test_can_render_blank_content_type():
    result = readme.render("wild thing", "")
    assert result == "<p>wild thing</p>\n"


def test_renderer_version():
    assert readme.renderer_version().startswith("readme-renderer==")


def test_renderer_version_includes_dependency_versions(fake_distributions):
    fake_distributions(
        {
            "readme-renderer": "45.0",
            "docutils": "0.23",
            "Pygments": "2.20.0",
            "nh3": "0.3.6",
            # "cmarkgfm" is deliberately absent, to verify it's skipped.
            "comrak": "0.0.12",
        }
    )

    assert readme.renderer_version() == (
        "readme-renderer==45.0,docutils==0.23,Pygments==2.20.0,"
        "nh3==0.3.6,comrak==0.0.12"
    )


def test_renderer_version_changes_with_dependency_version(fake_distributions):
    fake_distributions(
        {
            "readme-renderer": "45.0",
            "docutils": "0.23",
            "Pygments": "2.20.0",
            "nh3": "0.3.6",
            "comrak": "0.0.12",
        }
    )

    original_version = readme.renderer_version()

    readme.renderer_version.cache_clear()
    fake_distributions(
        {
            "readme-renderer": "45.0",
            "docutils": "0.23",
            "Pygments": "2.20.0",
            "nh3": "0.3.6",
            "comrak": "0.0.13",  # Only the dependency version changed.
        }
    )

    assert readme.renderer_version() != original_version
