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

import pytest

from warehouse.packaging.models import ProjectFactory

from ..common.db.packaging import (
    ProjectFactory as DBProjectFactory, ReleaseFactory as DBReleaseFactory,
)


class TestProjectFactory:

    @pytest.mark.parametrize(
        ("name", "normalized"),
        [
            ("foo", "foo"),
            ("Bar", "bar"),
        ],
    )
    def test_traversal_finds(self, db_request, name, normalized):
        project = DBProjectFactory.create(
            session=db_request.db, name=name, normalized_name=normalized,
        )
        root = ProjectFactory(db_request)

        assert root[normalized] == project

    def test_travel_cant_find(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)
        root = ProjectFactory(db_request)

        with pytest.raises(KeyError):
            root[project.name + "invalid"]


class TestProject:

    def test_traversal_finds(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)
        release = DBReleaseFactory.create(
            session=db_request.db, project=project,
        )

        assert project[release.version] == release

    def test_traversal_cant_find(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)

        with pytest.raises(KeyError):
            project["1.0"]
