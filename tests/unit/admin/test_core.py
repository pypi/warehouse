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

from warehouse.accounts import views as accounts_views
from warehouse.admin import includeme


def test_includeme():
    config = pretend.stub(
        add_jinja2_search_path=pretend.call_recorder(lambda path, name: None),
        add_static_view=pretend.call_recorder(
            lambda name, path, cache_max_age: None,
        ),
        include=pretend.call_recorder(lambda name: None),
        add_view=pretend.call_recorder(lambda *a, **kw: None),
    )

    includeme(config)

    assert config.add_jinja2_search_path.calls == [
        pretend.call("templates", name=".html"),
    ]
    assert config.add_static_view.calls == [
        pretend.call("admin/static", "static", cache_max_age=0),
    ]
    assert config.include.calls == [pretend.call(".routes")]
    assert config.add_view.calls == [
        pretend.call(
            accounts_views.login,
            route_name="admin.login",
            renderer="admin/login.html",
            uses_session=True,
            require_csrf=True,
            require_methods=False,
        ),
        pretend.call(
            accounts_views.logout,
            route_name="admin.logout",
            renderer="admin/logout.html",
            uses_session=True,
            require_csrf=True,
            require_methods=False,
        ),
    ]
