# Copyright 2014 Donald Stufft
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

import pretend

from warehouse.middlewares import XForwardedTokenMiddleware


def test_xforwardedtokenmiddleware_valid():
    response = pretend.stub()
    start_response = pretend.stub()
    app = pretend.call_recorder(lambda environ, start_response: response)

    middleware = XForwardedTokenMiddleware(app, "1234")
    resp = middleware(
        {
            "HTTP_X_WAREHOUSE_ACCESS_TOKEN": "1234",
            "HTTP_X_FORWARDED_FOR": "192.168.1.1",
        },
        start_response,
    )

    assert resp is response
    assert app.calls == [
        pretend.call(
            {"HTTP_X_FORWARDED_FOR": "192.168.1.1"},
            start_response,
        ),
    ]


def test_xforwardedtokenmiddleware_invalid():
    response = pretend.stub()
    start_response = pretend.stub()
    app = pretend.call_recorder(lambda environ, start_response: response)

    middleware = XForwardedTokenMiddleware(app, "1234")
    resp = middleware(
        {
            "HTTP_X_WAREHOUSE_ACCESS_TOKEN": "invalid",
            "HTTP_X_FORWARDED_FOR": "192.168.1.1",
        },
        start_response,
    )

    assert resp is response
    assert app.calls == [pretend.call({}, start_response)]
