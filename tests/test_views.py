# Copyright 2013 Donald Stufft
#
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

from warehouse.views import index

from .lib.db import ProjectFactory, ReleaseFactory, ReleaseFileFactory


def unique(iterable, key=None):
    seen = set()
    for item in iterable:
        k = key(item) if key is not None else item
        if k not in seen:
            seen.add(k)
            yield item


def test_index(dbapp):
    project1 = ProjectFactory.create(engine=dbapp.engine)
    project2 = ProjectFactory.create(engine=dbapp.engine)

    project1_release1 = ReleaseFactory.create(
        name=project1["name"],
        engine=dbapp.engine,
    )
    project1_release2 = ReleaseFactory.create(
        name=project1["name"],
        engine=dbapp.engine,
    )
    project2_release1 = ReleaseFactory.create(
        name=project2["name"],
        engine=dbapp.engine,
    )

    project1_release1_file1 = ReleaseFileFactory.create(
        name=project1["name"],
        version=project1_release1["version"],
        engine=dbapp.engine,
    )
    project1_release2_file1 = ReleaseFileFactory.create(
        name=project1["name"],
        version=project1_release2["version"],
        engine=dbapp.engine,
    )
    project2_release1_file1 = ReleaseFileFactory.create(
        name=project2["name"],
        version=project2_release1["version"],
        engine=dbapp.engine,
    )

    request = pretend.stub()

    resp = index(dbapp, request)

    assert resp.response.template.name == "index.html"
    assert resp.response.context == {
        "project_count": 2,
        "download_count": sum(
            x["downloads"]
            for x in [
                project1_release1_file1,
                project1_release2_file1,
                project2_release1_file1,
            ]
        ),
        "recently_updated": list(unique(
            sorted(
                [
                    project1_release1,
                    project1_release2,
                    project2_release1,
                ],
                key=lambda r: r["created"],
                reverse=True,
            ),
            key=lambda r: r["name"],
        )),
    }
