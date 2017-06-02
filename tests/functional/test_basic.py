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

import html5lib

from .pages import IndexPage


def test_robots_txt(webtest):
    resp = webtest.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.content_type == "text/plain"
    assert resp.body.decode(resp.charset) == (
        "Sitemap: http://localhost/sitemap.xml\n\n"
        "User-agent: *\n"
        "Disallow: /simple/\n"
        "Disallow: /packages/\n"
        "Disallow: /_includes/\n"
        "Disallow: /pypi/*/json\n"
        "Disallow: /pypi/*/*/json\n"
        "Disallow: /pypi*?\n"
    )


class TestLoginIndicator:

    def test_indicator_shows_not_logged_in(self, server_url, browser):
        # Navigate to our index page
        page = IndexPage(browser, base_url=server_url)
        page.visit()

        # Pull the HTML out and parse it using html5lib
        html = page.q(css="html").html[0]
        document = html5lib.parse(html, namespaceHTMLElements=False)

        # Ensure that our links are what we expect
        urls = [
            a.get("href")
            for a in document.findall(".//nav[@id='user-indicator']/a")
        ]
        assert urls == ["/account/login/",
                        "/account/register/",
                        "/help/",
                        "https://donate.pypi.io"]
