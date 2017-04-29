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

from warehouse.admin.views import core as views


class TestForbidden(object):

    def test_calls_real(self, monkeypatch):
        response = pretend.stub()
        forbidden_view = pretend.call_recorder(lambda *a, **kw: response)
        monkeypatch.setattr(views, "forbidden_view", forbidden_view)

        exc = pretend.stub()
        request = pretend.stub()

        assert views.forbidden(exc, request) is response
        assert forbidden_view.calls == [
            pretend.call(exc, request, redirect_to="admin.login"),
        ]


class TestDashboard(object):

    def test_dashboard(self):
        assert views.dashboard(pretend.stub()) == {}
