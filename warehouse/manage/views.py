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

from pyramid.security import Authenticated
from pyramid.view import view_config


@view_config(
    route_name="manage.profile",
    renderer="manage/profile.html",
    uses_session=True,
    effective_principals=Authenticated,
)
def manage_profile(request):
    return {}


@view_config(
    route_name="manage.projects",
    renderer="manage/projects.html",
    uses_session=True,
    effective_principals=Authenticated,
)
def manage_projects(request):
    return {}


@view_config(
    route_name="manage.project.settings",
    renderer="manage/project.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_settings(project, request):
    return {"project": project}
