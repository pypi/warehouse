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


def test_non_existent_route_404(webtest):
    resp = webtest.get("/asdadadasdasd/", status=404)
    assert resp.status_code == 404
