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

from warehouse.admin.routes import includeme


def test_includeme():
    config = pretend.stub(
        add_route=pretend.call_recorder(lambda *a, **k: None),
        get_settings=lambda: {"warehouse.domain": "w.local"},
    )

    includeme(config)

    config.add_route.calls == [
        pretend.call("admin.dashboard", "/admin/", domain="w.local"),
        pretend.call("admin.login", "/admin/login/", domain="w.local"),
        pretend.call("admin.logout", "/admin/logout/", domain="w.local"),
    ]
