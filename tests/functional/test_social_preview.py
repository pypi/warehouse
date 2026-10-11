# SPDX-License-Identifier: Apache-2.0

"""
Tests for the OpenGraph / Twitter Card metadata used to render link previews
on social and chat platforms.

Link-preview crawlers do not execute JavaScript and read only the document
head, so these tags are the entire preview payload. See:
https://ogp.me/

To regenerate the card images themselves, see
``docs/dev/development/frontend.md``.
"""

import datetime
import struct

from http import HTTPStatus
from pathlib import Path

import pytest

import warehouse

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory, ReleaseFactory

OG_CARD_WIDTH = "1200"
OG_CARD_HEIGHT = "630"
IMAGES = Path(warehouse.__path__[0]) / "static" / "images"


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height out of a PNG's IHDR chunk."""
    with path.open("rb") as f:
        header = f.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _meta(resp, **attrs) -> str | None:
    """Return the content of the meta tag matching ``attrs``, or None."""
    tag = resp.html.find("meta", attrs=attrs)
    return tag.get("content") if tag else None


def _project_page(webtest, **release_kwargs):
    """Create a project with one release and fetch its detail page."""
    created = release_kwargs.pop("created", None)
    project = ProjectFactory.create(**({"created": created} if created else {}))
    ReleaseFactory.create(project=project, **release_kwargs)
    resp = webtest.get(f"/project/{project.name}/", status=HTTPStatus.OK)
    return project, resp


ESTABLISHED = datetime.datetime.now() - datetime.timedelta(days=60)


@pytest.mark.parametrize("name", ["og-card.png", "og-card-test.png"])
def test_preview_card_assets_match_the_declared_dimensions(name):
    """
    Guards the pair. The dimensions are declared in ``base.html`` but live in
    the image files, so replacing an asset with a differently sized one would
    otherwise make the declared metadata wrong without failing anything.
    """
    path = IMAGES / name
    assert path.is_file()

    assert _png_dimensions(path) == (int(OG_CARD_WIDTH), int(OG_CARD_HEIGHT))


def test_project_page_carries_the_preview_card(webtest):
    """
    An established project gets the full card: the 1200x630 image rather than
    the old small square logo, with dimensions declared so a crawler can lay
    it out without fetching and measuring the image first.
    """
    _, resp = _project_page(webtest, created=ESTABLISHED)

    image = _meta(resp, property="og:image")
    assert image is not None
    assert "og-card" in image
    assert image.startswith("http")
    assert _meta(resp, property="og:image:width") == OG_CARD_WIDTH
    assert _meta(resp, property="og:image:height") == OG_CARD_HEIGHT
    assert _meta(resp, property="og:image:alt")
    assert _meta(resp, name="twitter:card") == "summary_large_image"
    assert _meta(resp, name="googlebot") is None


def test_project_page_og_description_uses_the_release_summary(webtest):
    """
    Also guards against stray whitespace: the ``description`` block renders
    into a ``content`` attribute, so reflowing it across lines would embed
    newlines in the preview card's description text.
    """
    _, resp = _project_page(webtest, created=ESTABLISHED, summary="A short summary.")

    assert _meta(resp, property="og:description") == "A short summary."


@pytest.mark.parametrize("summary", [None, "   "], ids=["missing", "whitespace-only"])
def test_project_page_og_description_falls_back_without_a_summary(webtest, summary):
    """
    ``Release.summary`` is nullable and Jinja has no ``finalize`` configured,
    so an absent summary rendered the literal string "None" into both the SEO
    description and the preview card. A whitespace-only summary is as blank on
    a card as no summary at all.
    """
    project, resp = _project_page(webtest, created=ESTABLISHED, summary=summary)

    description = _meta(resp, property="og:description")
    assert description is not None
    assert description.strip() != ""
    assert project.name in description


def test_homepage_carries_a_complete_preview(webtest):
    """
    The card is the site-wide default rather than a project-page special case.

    ``index.html`` overrides ``title_base`` without defining ``title``, which
    left ``og:title`` empty until ``default`` was given ``boolean=True`` --
    the site's most-shared URL previewing as a large card with no title.

    X reads alt text only from ``twitter:image:alt``; unlike title,
    description and image, it does not fall back to the og: equivalent.
    """
    resp = webtest.get("/", status=HTTPStatus.OK)

    image = _meta(resp, property="og:image")
    assert image is not None
    assert "og-card" in image
    assert _meta(resp, property="og:image:width") == OG_CARD_WIDTH
    assert _meta(resp, property="og:image:height") == OG_CARD_HEIGHT
    assert _meta(resp, name="twitter:card") == "summary_large_image"

    title = _meta(resp, property="og:title")
    assert title is not None
    assert title.strip() != ""

    assert _meta(resp, name="twitter:image:alt") == _meta(resp, property="og:image:alt")


def test_page_overriding_the_preview_image_replaces_the_whole_group(webtest):
    """
    The image and the tags describing it are emitted as one unit, so a page
    supplying its own image cannot inherit the card's dimensions and describe
    its image incorrectly.

    Also checks that neither the overridden description nor the overridden alt
    text carries the indentation of its block.
    """
    resp = webtest.get("/security-key-giveaway/", status=HTTPStatus.OK)

    image = _meta(resp, property="og:image")
    assert image is not None
    assert "titan" in image
    assert _meta(resp, property="og:image:width") == "2785"
    assert _meta(resp, property="og:image:height") == "1392"

    for value in (
        _meta(resp, property="og:description"),
        _meta(resp, property="og:image:alt"),
    ):
        assert value is not None
        assert value == value.strip()
        assert "\n" not in value


def test_error_pages_do_not_lend_the_official_card(webtest):
    """
    A dead or mistyped URL should not preview as an official full-width card
    promising a working package repository.

    Dropping ``og:image`` matters more than the card type: Slack, Discord,
    Facebook and LinkedIn read ``og:image`` and ignore ``twitter:card``, so
    downgrading only the latter would still hand them the branded card.
    """
    resp = webtest.get("/no-such-page-xyzzy/", status=HTTPStatus.NOT_FOUND)

    assert _meta(resp, property="og:image") is None
    assert _meta(resp, property="og:image:width") is None
    assert _meta(resp, property="og:image:height") is None
    assert _meta(resp, name="twitter:card") == "summary"


def test_recently_created_project_does_not_lend_the_official_card(webtest):
    """
    Mirrors the existing ``noindex`` window. Brand-new projects are
    disproportionately typosquats and malware, so preview trust is withheld
    for as long as search trust is, and one flag drives both.
    """
    _, resp = _project_page(webtest)

    assert _meta(resp, name="googlebot") == "noindex"
    assert _meta(resp, property="og:image") is None
    assert _meta(resp, property="og:image:width") is None
    assert _meta(resp, name="twitter:card") == "summary"


def test_testpypi_uses_its_own_card_and_site_name(testpypi_webtest):
    """
    TestPyPI links must not be visually indistinguishable from real PyPI
    packages when shared.
    """
    resp = testpypi_webtest.get("/", status=HTTPStatus.OK)

    assert _meta(resp, property="og:site_name") == "TestPyPI"
    image = _meta(resp, property="og:image")
    assert image is not None
    assert "og-card-test" in image
    alt = _meta(resp, property="og:image:alt")
    assert alt is not None
    assert "TestPyPI" in alt


def test_recently_joined_user_profile_does_not_lend_the_official_card(webtest):
    """
    User profiles carry the same ``is_recent`` noindex window as projects, so
    they withhold the card on the same terms.
    """
    user = UserFactory.create(date_joined=datetime.datetime.now())

    resp = webtest.get(f"/user/{user.username}/", status=HTTPStatus.OK)

    assert _meta(resp, name="googlebot") == "noindex"
    assert _meta(resp, property="og:image") is None
    assert _meta(resp, name="twitter:card") == "summary"


def test_established_user_profile_carries_the_preview_card(webtest):
    user = UserFactory.create(date_joined=ESTABLISHED)

    resp = webtest.get(f"/user/{user.username}/", status=HTTPStatus.OK)

    assert _meta(resp, name="googlebot") is None
    image = _meta(resp, property="og:image")
    assert image is not None
    assert "og-card" in image
    assert _meta(resp, name="twitter:card") == "summary_large_image"
