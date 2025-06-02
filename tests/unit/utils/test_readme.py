# SPDX-License-Identifier: Apache-2.0

from warehouse.utils import readme


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
    assert readme.renderer_version() is not None
