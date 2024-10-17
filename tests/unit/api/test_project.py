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

import pretend

from pyramid.httpexceptions import HTTPForbidden

from warehouse.api import project


def test_fails_in_read_only_mode(pyramid_request):
    pyramid_request.flags = pretend.stub(enabled=lambda *a: True)

    with pytest.raises(HTTPForbidden) as excinfo:
        project.json_release_modify(None, pyramid_request)

    resp = excinfo.value

    assert resp.status_code == 403
    assert resp.status == ("403 Read-only mode: Project modifications are temporarily disabled.")
