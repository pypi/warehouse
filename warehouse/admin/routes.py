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


def includeme(config):
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    warehouse = config.get_settings().get("warehouse.domain")

    # General Admin pages
    config.add_route("admin.dashboard", "/admin/", domain=warehouse)
    config.add_route("admin.login", "/admin/login/", domain=warehouse)
    config.add_route("admin.logout", "/admin/logout/", domain=warehouse)

    # User related Admin pages
    config.add_route("admin.user.list", "/admin/users/", domain=warehouse)
    config.add_route(
        "admin.user.detail",
        "/admin/users/{user_id}/",
        domain=warehouse,
    )

    # Project related Admin pages
    config.add_route(
        "admin.project.list",
        "/admin/projects/",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.detail",
        "/admin/projects/{project_name}/",
        domain=warehouse,
    )
