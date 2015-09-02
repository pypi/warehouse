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

import packaging.version

from warehouse.cli.search.reindex import reindex, _project_docs

from ....common.db.packaging import ProjectFactory, ReleaseFactory


def test_project_docs(db_session):
    projects = [ProjectFactory.create() for _ in range(2)]
    releases = {
        p: sorted(
            [ReleaseFactory.create(project=p) for _ in range(3)],
            key=lambda r: packaging.version.parse(r.version),
            reverse=True,
        )
        for p in projects
    }

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_type": "project",
            "_source": {
                "name": p.name,
                "name.normalized": p.normalized_name,
                "version": [r.version for r in prs],
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].name)
    ]
