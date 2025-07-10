# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from warehouse.packaging.search import Project


def test_build_search():
    release = pretend.stub(
        name="Foobar",
        normalized_name="foobar",
        summary="This is my summary",
        description="This is my description",
        author="Jane Author",
        author_email="jane.author@example.com",
        maintainer="Joe Maintainer",
        maintainer_email="joe.maintainer@example.com",
        home_page="https://example.com/foobar/",
        download_url="https://example.com/foobar/downloads/",
        keywords="the, keywords, lol",
        platform="any platform",
        created=datetime.datetime(1956, 1, 31),
        classifiers=["Alpha", "Beta"],
    )
    obj = Project.from_db(release)

    assert obj.meta.id == "foobar"
    assert obj["name"] == "Foobar"
    assert obj["summary"] == "This is my summary"
    assert obj["description"] == "This is my description"
    assert obj["author"] == "Jane Author"
    assert obj["author_email"] == "jane.author@example.com"
    assert obj["maintainer"] == "Joe Maintainer"
    assert obj["maintainer_email"] == "joe.maintainer@example.com"
    assert obj["home_page"] == "https://example.com/foobar/"
    assert obj["download_url"] == "https://example.com/foobar/downloads/"
    assert obj["keywords"] == "the, keywords, lol"
    assert obj["platform"] == "any platform"
    assert obj["created"] == datetime.datetime(1956, 1, 31)
    assert obj["classifiers"] == ["Alpha", "Beta"]
