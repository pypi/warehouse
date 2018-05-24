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

from warehouse.sitemap import views as sitemap
from ...common.db.accounts import UserFactory
from ...common.db.packaging import ProjectFactory


def test_sitemap_index(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    project = ProjectFactory.create(name="foobar")
    users = [UserFactory.create(username="a"), UserFactory.create(username="b")]

    # Have to pass this here, because passing date_joined=None to the create
    # function above makes the factory think it needs to generate a random
    # date.
    users[1].date_joined = None
    db_request.db.flush()

    assert sitemap.sitemap_index(db_request) == {
        "buckets": [
            sitemap.Bucket("0", modified=project.created),
            sitemap.Bucket("1", modified=users[0].date_joined),
            sitemap.Bucket("5", modified=None),
        ]
    }
    assert db_request.response.content_type == "text/xml"


def test_sitemap_bucket(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    expected = ["/project/foobar/"]
    expected_iter = iter(expected)
    db_request.route_url = pretend.call_recorder(lambda *a, **kw: next(expected_iter))

    db_request.matchdict["bucket"] = "0"

    ProjectFactory.create(name="foobar")
    UserFactory.create(username="a")
    UserFactory.create(username="b")

    assert sitemap.sitemap_bucket(db_request) == {"urls": ["/project/foobar/"]}
    assert db_request.response.content_type == "text/xml"


def test_sitemap_bucket_too_many(monkeypatch, db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    db_request.route_url = pretend.call_recorder(lambda *a, **kw: "/")
    db_request.matchdict["bucket"] = "5"

    monkeypatch.setattr(sitemap, "SITEMAP_MAXSIZE", 2)

    for _ in range(3):
        p = ProjectFactory.create()
        p.sitemap_bucket = "5"

    db_request.db.flush()

    with pytest.raises(ValueError):
        sitemap.sitemap_bucket(db_request)
