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

from ...common.db.sponsors import SponsorFactory


def test_sponsor_color_logo_img_tag(db_request):
    sponsor = SponsorFactory.create()
    expected = (
        f'<img src="{sponsor.color_logo_url}"'
        + f' alt="{sponsor.name}" loading="lazy">'
    )
    assert sponsor.color_logo_img == expected


def test_sponsor_white_logo_img_tag(db_request):
    sponsor = SponsorFactory.create()
    expected = (
        f'<img class="sponsors__image" src="{sponsor.white_logo_url}"'
        + f' alt="{sponsor.name}" loading="lazy">'
    )
    assert sponsor.white_logo_img == expected

    # should return empty string if no white logo
    sponsor.white_logo_url = None
    assert sponsor.white_logo_img == ""


def test_activity_property_render_markdown_content(db_request):
    sponsor = SponsorFactory.create()
    sponsor.activity_markdown = "Paragraph1\n\nParagraph2"
    expected = "<p>Paragraph1</p>\n<p>Paragraph2</p>"
    assert sponsor.activity.strip() == expected.strip()
    # empty string if no data
    sponsor.activity_markdown = None
    assert sponsor.activity == ""


# sanitization is implemented internally in readme library
# ref: https://github.com/pypa/readme_renderer/blob/main/readme_renderer/clean.py
# this test is just so we can be more secure about it
def test_ensure_activity_markdown_is_safe_against_xss(db_request):
    sponsor = SponsorFactory.create()
    sponsor.activity_markdown = r"[XSS](javascript://www.google.com%0Aprompt(1))"
    expected = '<p><a rel="nofollow">XSS</a></p>'
    assert sponsor.activity.strip() == expected.strip()
    # empty string if no data
    sponsor.activity_markdown = None
    assert sponsor.activity == ""
