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

import logging

from sqlalchemy import select

from warehouse.packaging.models import Project
from warehouse.utils.db import query_printer


def test_print_query_renders_params(caplog):
    caplog.set_level(logging.DEBUG)

    query = select(Project.id, Project.name).where(Project.name == "value")
    assert "WHERE projects.name = :name_1" in str(query)

    query_printer.print_query(query)

    assert ":name_1" not in caplog.text
    assert "WHERE projects.name = 'value'" in caplog.text
