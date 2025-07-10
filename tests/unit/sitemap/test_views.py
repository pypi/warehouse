# SPDX-License-Identifier: Apache-2.0

import datetime

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

    project = ProjectFactory.create(
        name="foobar",
        created=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)),
    )
    users = [
        UserFactory.create(
            username="a",
            date_joined=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
            ),
        ),
        UserFactory.create(username="b"),
        UserFactory.create(
            username="c", date_joined=(datetime.datetime.now(datetime.UTC))
        ),
    ]

    # Have to pass this here, because passing date_joined=None to the create
    # function above makes the factory think it needs to generate a random
    # date.
    users[1].date_joined = None
    db_request.db.flush()

    assert sitemap.sitemap_index(db_request) == {
        "buckets": [
            sitemap.Bucket("0a", modified=project.created),
            sitemap.Bucket("1f", modified=users[0].date_joined),
            sitemap.Bucket("52", modified=None),
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

    db_request.matchdict["bucket"] = "0a"

    ProjectFactory.create(
        name="foobar",
        created=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)),
    )
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
    db_request.matchdict["bucket"] = "52"

    monkeypatch.setattr(sitemap, "SITEMAP_MAXSIZE", 2)

    for _ in range(3):
        p = ProjectFactory.create(
            created=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15))
        )
        p.sitemap_bucket = "52"

    db_request.db.flush()

    with pytest.raises(sitemap.BucketTooSmallError):
        sitemap.sitemap_bucket(db_request)
