# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend
import pytest

from warehouse.rss import views as rss

from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_rss_updates(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    db_request.session = pretend.stub()

    project1 = ProjectFactory.create()
    project2 = ProjectFactory.create()

    release1 = ReleaseFactory.create(project=project1)
    release1.created = datetime.date(2011, 1, 1)
    release2 = ReleaseFactory.create(project=project2)
    release2.created = datetime.date(2012, 1, 1)
    release2.author_email = "noreply@pypi.org"
    release3 = ReleaseFactory.create(project=project1)
    release3.created = datetime.date(2013, 1, 1)

    assert rss.rss_updates(db_request) == {
        "latest_releases": tuple(
            zip((release3, release2, release1), (None, "noreply@pypi.org", None))
        )
    }
    assert db_request.response.content_type == "text/xml"


def test_rss_packages(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    db_request.session = pretend.stub()

    project1 = ProjectFactory.create()
    project1.created = datetime.date(2011, 1, 1)
    ReleaseFactory.create(project=project1)

    project2 = ProjectFactory.create()
    project2.created = datetime.date(2012, 1, 1)

    project3 = ProjectFactory.create()
    project3.created = datetime.date(2013, 1, 1)
    ReleaseFactory.create(project=project3)

    assert rss.rss_packages(db_request) == {
        "newest_projects": tuple(zip((project3, project1), (None, None)))
    }
    assert db_request.response.content_type == "text/xml"


def test_rss_project_releases(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    db_request.session = pretend.stub()

    project = ProjectFactory.create()

    release_v1 = ReleaseFactory.create(project=project, version="1.0.0")
    release_v1.created = datetime.date(2018, 1, 1)
    release_v3 = ReleaseFactory.create(project=project, version="3.0.0")
    release_v3.created = datetime.date(2019, 1, 1)
    release_v2 = ReleaseFactory.create(project=project, version="2.0.0")
    release_v2.created = datetime.date(2020, 1, 1)

    release_v3.author_email = "noreply@pypi.org"

    assert rss.rss_project_releases(project, db_request) == {
        "project": project,
        "latest_releases": tuple(
            zip((release_v2, release_v3, release_v1), (None, "noreply@pypi.org", None))
        ),
    }
    assert db_request.response.content_type == "text/xml"


@pytest.mark.parametrize(
    ("author_email", "expected"),
    [
        (None, None),
        ("", None),
        ("UNKNOWN", None),
        ("noreply@pypi.org, UNKNOWN", None),
        ("noreply@pypi.org", "noreply@pypi.org"),
        ("No Reply <noreply@pypi.org>", "noreply@pypi.org"),
        (
            (
                # simple, no spaces
                "noreply@pypi.org,"
                # space after
                "noreply@pypi.org ,"
                # space before, incl realname
                " No Reply <noreply@pypi.org>,"
                # two spaces before, angle brackets
                "  <noreply@pypi.org>"
            ),
            ", ".join(["noreply@pypi.org"] * 4),
        ),
    ],
)
def test_format_author(db_request, author_email, expected):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )
    db_request.session = pretend.stub()

    release = ReleaseFactory.create()

    release.author_email = author_email
    assert rss._format_author(release) == expected
