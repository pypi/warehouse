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

import pretend
import pytest

from warehouse.legacy import pypi


@pytest.mark.parametrize("content_type", [None, "text/html", "__empty__"])
def test_pypi_index(content_type):
    headers = {}

    if content_type != "__empty__":
        headers["Content-Type"] = content_type

    app = pretend.stub()
    request = pretend.stub(
        headers=headers,
        url_adapter=pretend.stub(
            build=pretend.call_recorder(
                lambda *a, **kw: "/",
            ),
        ),
    )
    # request for /pypi with no additional request information redirects
    # to site root
    #
    resp = pypi.pypi(app, request)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/"
    assert request.url_adapter.build.calls == [
        pretend.call(
            "warehouse.views.index",
            {},
            force_external=False,
        ),
    ]


def test_pypi_route_xmlrpc(monkeypatch):
    app = pretend.stub()
    request = pretend.stub(
        headers={'Content-Type': 'text/xml'},
    )

    xmlrpc = pretend.stub(
        handle_request=pretend.call_recorder(lambda *a: 'success')
    )
    monkeypatch.setattr(pypi, 'xmlrpc', xmlrpc)

    # request for /pypi with no additional request information redirects
    # to site root
    #
    resp = pypi.pypi(app, request)

    assert xmlrpc.handle_request.calls == [pretend.call(app, request)]
    assert resp == 'success'
