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

from warehouse import sitemap
from ..common.db.accounts import UserFactory
from ..common.db.packaging import ProjectFactory


@pytest.mark.parametrize(
    ("url", "bucket"),
    [
        ("https://example.com/foo/bar/", "9"),
        ("https://example.com/one/two/", "f"),
        ("https://example.com/up/down/", "6"),
        ("https://example.com/left/right/", "1"),
        ("https://example.com/no/yes/", "2"),
    ],
)
def test_url2bucket(url, bucket):
    assert sitemap._url2bucket(url) == bucket


def test_generate_urls(db_request):
    expected = ["/", "/project/foobar/", "/user/jarjar/"]
    expected_iter = iter(expected)
    db_request.route_url = pretend.call_recorder(
        lambda *a, **kw: next(expected_iter)
    )

    project = ProjectFactory.create()
    user = UserFactory.create()

    urls = list(sitemap._generate_urls(db_request))
    assert urls == [
        sitemap.SitemapURL(url="/", modified=None),
        sitemap.SitemapURL(url="/project/foobar/", modified=project.created),
        sitemap.SitemapURL(url="/user/jarjar/", modified=user.date_joined),
    ]
    assert db_request.route_url.calls == [
        pretend.call("index"),
        pretend.call("packaging.project", name=project.normalized_name),
        pretend.call("accounts.profile", username=user.username),
    ]


def test_sitemap_index(db_request):
    expected = ["/", "/project/foobar/", "/user/jarjar/", "/user/jarjar/"]
    expected_iter = iter(expected)
    db_request.route_url = pretend.call_recorder(
        lambda *a, **kw: next(expected_iter)
    )

    project = ProjectFactory.create()
    users = [
        UserFactory.create(username="a"),
        UserFactory.create(username="b"),
    ]

    # Have to pass this here, because passing date_joined=None to the create
    # function above makes the factory think it needs to generate a random
    # date.
    users[1].date_joined = None
    db_request.db.flush()

    assert sitemap.sitemap_index(db_request) == {
        "buckets": [
            sitemap.Bucket("5", modified=None),
            sitemap.Bucket("6", modified=users[0].date_joined),
            sitemap.Bucket("c", modified=project.created),
        ],
    }
    assert db_request.response.content_type == "text/xml"


def test_sitemap_bucket(db_request):
    expected = ["/", "/project/foobar/", "/user/jarjar/"]
    expected_iter = iter(expected)
    db_request.route_url = pretend.call_recorder(
        lambda *a, **kw: next(expected_iter)
    )

    db_request.matchdict["bucket"] = "c"

    ProjectFactory.create()
    UserFactory.create()

    assert sitemap.sitemap_bucket(db_request) == {"urls": ["/project/foobar/"]}
    assert db_request.response.content_type == "text/xml"


def test_sitemap_bucket_too_many(monkeypatch, db_request):
    db_request.route_url = pretend.call_recorder(lambda *a, **kw: "/")
    db_request.matchdict["bucket"] = "5"

    monkeypatch.setattr(sitemap, "SITEMAP_MAXSIZE", 2)

    for _ in range(3):
        ProjectFactory.create()

    with pytest.raises(ValueError):
        sitemap.sitemap_bucket(db_request)
