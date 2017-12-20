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

from warehouse.manage import views


class TestManageProfile:

    def test_manage_profile(self):
        request = pretend.stub()

        assert views.manage_profile(request) == {}


class TestManageProjects:

    def test_manage_projects(self):
        request = pretend.stub()

        assert views.manage_projects(request) == {}


class TestManageProjectSettings:

    def test_manage_project_settings(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_settings(project, request) == {
            "project": project,
        }
