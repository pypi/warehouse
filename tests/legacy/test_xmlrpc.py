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


@pytest.mark.parametrize(("hidden", "result"), [
    (True, ['1', '2', '3', '4']),
    (False, ['1', '2', '3']),
])
def test_xmlrpc_package_releases(hidden, result):
    if hidden:
        result = ['1', '2', '3', '4']
    else:
        result = ['1', '2', '3']

    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_project_versions=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    if hidden:
        r = interface.package_releases('name', True)
        assert app.models.packaging.get_project_versions.calls == [
            pretend.call('name', True)
        ]
    else:
        r = interface.package_releases('name')
        assert app.models.packaging.get_project_versions.calls == [
            pretend.call('name', False)
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


@pytest.mark.parametrize("pgp", [True, False])
def test_release_urls(pgp, monkeypatch):
    downloads = [
        dict(
            name="spam",
            url='/packages/source/t/spam/spam-1.0.tar.gz',
            version="1.0",
            filename="spam-1.0.tar.gz",
            python_version="source",
            packagetype="sdist",
            md5_digest="0cc175b9c0f1b6a831c399e269772661",
            downloads=10,
            size=1234,
            pgp_url='/packages/source/t/spam/spam-1.0.tar.gz.sig'
                if pgp else None,
            comment_text='download for great justice',
        ),
        dict(
            name="spam",
            url='/packages/source/t/spam/spam-1.0.zip',
            version="1.0",
            filename="spam-1.0.zip",
            python_version="source",
            packagetype="sdist",
            md5_digest="0cc175b3c0f1b6a831c399e269772661",
            downloads=12,
            size=1235,
            pgp_url='/packages/source/t/spam/spam-1.0.zip.sig'
                if pgp else None,
            comment_text=None,
        )
    ]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_downloads=pretend.call_recorder(lambda *a: downloads),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    result = interface.release_urls('spam', '1.0')

    assert app.models.packaging.get_downloads.calls == [
        pretend.call('spam', '1.0'),
    ]
    assert result == [
        dict(
            url='/packages/source/t/spam/spam-1.0.tar.gz',
            packagetype="sdist",
            filename="spam-1.0.tar.gz",
            size=1234,
            md5_digest="0cc175b9c0f1b6a831c399e269772661",
            downloads=10,
            has_sig=pgp,
            python_version="source",
            comment_text='download for great justice',
        ),
        dict(
            url='/packages/source/t/spam/spam-1.0.zip',
            packagetype="sdist",
            filename="spam-1.0.zip",
            size=1235,
            md5_digest="0cc175b3c0f1b6a831c399e269772661",
            downloads=12,
            has_sig=pgp,
            python_version="source",
            comment_text=None,
        )
    ]
