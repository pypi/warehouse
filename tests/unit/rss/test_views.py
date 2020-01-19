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

import datetime

import pretend

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

    release1 = ReleaseFactory.create(project=project)
    release1.created = datetime.date(2019, 1, 1)
    release2 = ReleaseFactory.create(project=project)
    release2.created = datetime.date(2019, 1, 2)
    release3 = ReleaseFactory.create(project=project)
    release3.created = datetime.date(2019, 1, 3)
    release3.author_email = "noreply@pypi.org"

    assert rss.rss_project_releases(project, db_request) == {
        "project": project,
        "latest_releases": tuple(
            zip((release3, release2, release1), ("noreply@pypi.org", None, None))
        ),
    }
    assert db_request.response.content_type == "text/xml"


def test_format_author(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(
            enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
        )
    )

    db_request.session = pretend.stub()

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    release.author_email = "noreply@pypi.org"
    assert rss._format_author(release) == release.author_email

    release.author_email = "No Reply <noreply@pypi.org>"
    assert rss._format_author(release) == "noreply@pypi.org"

    for invalid in (None, "", "UNKNOWN", "noreply@pypi.org, UNKNOWN"):
        release.author_email = invalid
        assert rss._format_author(release) is None

    release.author_email = (
        # simple, no spaces
        "noreply@pypi.org,"
        # space after
        "noreply@pypi.org ,"
        # space before, incl realname
        " No Reply <noreply@pypi.org>,"
        # two spaces before, angle brackets
        "  <noreply@pypi.org>"
    )
    assert rss._format_author(release) == ", ".join(["noreply@pypi.org"] * 4)
