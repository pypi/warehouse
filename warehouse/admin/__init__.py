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
    from warehouse.accounts.views import login, logout

    # Setup Jinja2 Rendering for the Admin application
    config.add_jinja2_search_path("templates", name=".html")

    # Setup our static assets
    config.add_static_view(
        "admin/static", "warehouse.admin:static/dist", cache_max_age=0
    )

    # Add our routes
    config.include(".routes")

    # Add our flags
    config.include(".flags")

    config.add_view(
        login,
        route_name="admin.login",
        renderer="admin/login.html",
        uses_session=True,
        require_csrf=True,
        require_methods=False,
    )
    config.add_view(
        logout,
        route_name="admin.logout",
        renderer="admin/logout.html",
        uses_session=True,
        require_csrf=True,
        require_methods=False,
    )
