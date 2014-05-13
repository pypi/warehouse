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

from warehouse.legacy.middlewares import LegacyRewriteMiddleware


def test_no_modification():
    app = pretend.call_recorder(lambda environ, start_response: None)
    LegacyRewriteMiddleware(app)({"PATH_INFO": "/foo/bar"}, None)

    assert app.calls == [pretend.call({"PATH_INFO": "/foo/bar"}, None)]


def test_pypi_passes_through():
    app = pretend.call_recorder(lambda environ, start_response: None)
    LegacyRewriteMiddleware(app)({"PATH_INFO": "/pypi"}, None)

    assert app.calls == [pretend.call({"PATH_INFO": "/pypi"}, None)]


def test_pypi_dispatches_xmlrpc():
    app = pretend.call_recorder(lambda environ, start_response: None)
    LegacyRewriteMiddleware(app)(
        {
            "PATH_INFO": "/pypi",
            "CONTENT_TYPE": "text/xml",
        },
        None,
    )

    assert app.calls == [
        pretend.call(
            {"PATH_INFO": "/_legacy/xmlrpc/", "CONTENT_TYPE": "text/xml"},
            None,
        ),
    ]
