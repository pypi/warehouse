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
        headers={'Content-Type': 'text/xml'},
        get_data=lambda **k: xml_request,
    )

    assert xmlrpc.handle_request(app, request) == 'response'

    assert interface.list_packages.calls
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


def test_xmlrpc_list_packages():
    all_projects = [Project("bar"), Project("foo")]

    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                all_projects=pretend.call_recorder(lambda: all_projects),
            ),
        ),
    )
    request = pretend.stub(
        headers={'Content-Type': 'text/xml'}
    )

    interface = xmlrpc.Interface(app, request)

    result = interface.list_packages()

    assert app.models.packaging.all_projects.calls == [pretend.call()]
    assert result == ['bar', 'foo']
