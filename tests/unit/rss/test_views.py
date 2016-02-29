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

from warehouse.rss import views as rss
from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_rss_updates(db_request):
    project1 = ProjectFactory.create()
    project2 = ProjectFactory.create()

    release1 = ReleaseFactory.create(project=project1)
    release1.created = datetime.date(2011, 1, 1)
    release2 = ReleaseFactory.create(project=project2)
    release2.created = datetime.date(2012, 1, 1)
    release3 = ReleaseFactory.create(project=project1)
    release3.created = datetime.date(2013, 1, 1)

    assert rss.rss_updates(db_request) == {
        "latest_releases": [release3, release2, release1],
    }
    assert db_request.response.content_type == "text/xml"


def test_rss_packages(db_request):
    project1 = ProjectFactory.create()
    project1.created = datetime.date(2011, 1, 1)
    ReleaseFactory.create(project=project1)

    project2 = ProjectFactory.create()
    project2.created = datetime.date(2012, 1, 1)

    project3 = ProjectFactory.create()
    project3.created = datetime.date(2013, 1, 1)
    ReleaseFactory.create(project=project3)

    assert rss.rss_packages(db_request) == {
        "newest_projects": [project3, project1],
    }
    assert db_request.response.content_type == "text/xml"
