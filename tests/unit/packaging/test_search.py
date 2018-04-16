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

from warehouse.packaging.search import Project


def test_build_search():
    release = pretend.stub(
        name="Foobar",
        normalized_name="foobar",
        all_versions=[
            "5.0.dev0",
            "4.0",
            "3.0",
            "2.0",
            "1.0",
        ],
        latest_version="4.0",
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
    assert obj["version"] == ["5.0.dev0", "4.0", "3.0", "2.0", "1.0"]
    assert obj["latest_version"] == "4.0"
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
    assert obj["classifiers"] == ['Alpha', 'Beta']
