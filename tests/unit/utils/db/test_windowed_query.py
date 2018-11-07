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

import math

import pytest

from warehouse.packaging.models import Project
from warehouse.utils.db.windowed_query import windowed_query

from ....common.db.packaging import ProjectFactory


@pytest.mark.parametrize("window_size", [1, 2])
def test_windowed_query(db_session, query_recorder, window_size):
    projects = {ProjectFactory.create() for _ in range(10)}
    expected = math.ceil(len(projects) / window_size) + 1

    query = db_session.query(Project)
    with query_recorder:
        assert set(windowed_query(query, Project.name, window_size)) == projects

    assert len(query_recorder.queries) == expected
