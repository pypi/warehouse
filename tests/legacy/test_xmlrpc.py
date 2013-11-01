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

from werkzeug.exceptions import BadRequest

from warehouse.packaging.models import Project
from warehouse.legacy import xmlrpc


def test_xmlrpc_handler(monkeypatch):
    Response = pretend.call_recorder(lambda *a, **k: 'response')
    monkeypatch.setattr(xmlrpc, "Response", Response)

    interface = pretend.stub(
        list_packages=pretend.call_recorder(lambda *a, **k: 'one two'.split())
    )
    Interface = lambda a, r: interface
    monkeypatch.setattr(xmlrpc, "Interface", Interface)

    app = pretend.stub()

    xml_request = '''<?xml version="1.0"?><methodCall>
        <methodName>list_packages</methodName></methodCall>'''

    request = pretend.stub(
        headers={
            'Content-Type': 'text/xml',
            'Content-Length': str(len(xml_request)),
        },
        get_data=lambda **k: xml_request,
    )

    assert xmlrpc.handle_request(app, request) == 'response'

    assert interface.list_packages.calls == [pretend.call()]
    response_xml = Response.calls[0].args[0]

    assert response_xml == u'''<?xml version='1.0'?>
<methodResponse>
<params>
<param>
<value><array><data>
<value><string>one</string></value>
<value><string>two</string></value>
</data></array></value>
</param>
</params>
</methodResponse>
'''
    assert Response.calls[0].kwargs == dict(mimetype='text/xml')


def test_xmlrpc_handler_size_limit(monkeypatch):
    app = pretend.stub()

    request = pretend.stub(
        headers={
            'Content-Type': 'text/xml',
            'Content-Length': str(10 * 1024 * 1024 + 1)
        },
    )

    with pytest.raises(BadRequest):
        xmlrpc.handle_request(app, request)


def test_xmlrpc_list_packages():
    all_projects = [Project("bar"), Project("foo")]

    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                all_projects=pretend.call_recorder(lambda: all_projects),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    result = interface.list_packages()

    assert app.models.packaging.all_projects.calls == [pretend.call()]
    assert result == ['bar', 'foo']


@pytest.mark.parametrize(("num", "result"), [
    (None, [('three', 10000), ('one', 1110), ('two', 22)]),
    (2, [('three', 10000), ('one', 1110)]),
])
def test_xmlrpc_top_packages(num, result):
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_top_projects=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    if num:
        r = interface.top_packages(num)
        assert app.models.packaging.get_top_projects.calls == [
            pretend.call(num)
        ]
    else:
        r = interface.top_packages()
        assert app.models.packaging.get_top_projects.calls == [
            pretend.call(None)
        ]

    assert r == result


def test_xmlrpc_list_packages_with_serial():
    d = dict(one=1, two=2, three=3)
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_projects_with_serial=pretend.call_recorder(lambda: d),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    result = interface.list_packages_with_serial()

    assert app.models.packaging.get_projects_with_serial.calls == [
        pretend.call(),
    ]
    assert result == d
