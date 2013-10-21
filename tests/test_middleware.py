# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import mock
import pretend

from warehouse.middleware import PoweredBy


def test_powered_by():
    app = pretend.call_recorder(lambda environ, start_response: start_response)
    powered_by = PoweredBy(app, "Test Powered By")

    environ = pretend.stub()
    start_response = pretend.call_recorder(lambda *a: None)

    powered_by(environ, start_response)(200, [])

    assert app.calls == [pretend.call(environ, mock.ANY)]
    assert start_response.calls == [
        pretend.call(200, [("X-Powered-By", "Test Powered By")], None),
    ]
