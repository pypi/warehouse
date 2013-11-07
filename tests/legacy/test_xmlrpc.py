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

import datetime

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


def test_xmlrpc_package_releases():
    result = ['1', '2', '3', '4']
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_project_versions=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.package_releases('name') == ['1', '2', '3', '4']

    assert app.models.packaging.get_project_versions.calls == [
        pretend.call('name')
    ]


@pytest.mark.parametrize("with_ids", [False, True])
def test_xmlrpc_changelog(with_ids):
    now = datetime.datetime.now()
    old = datetime.datetime.now() - datetime.timedelta(days=1)
    now_plus_1 = datetime.datetime.now() + datetime.timedelta(days=1)
    now_plus_2 = datetime.datetime.now() + datetime.timedelta(days=2)
    data = [
        dict(name='one', version='1', submitted_date=now,
            action='created', id=1),
        dict(name='two', version='2', submitted_date=now,
            action='new release', id=2),
        dict(name='one', version='2', submitted_date=now_plus_1,
            action='new release', id=3),
        dict(name='one', version='3', submitted_date=now_plus_2,
            action='new release', id=4),
    ]
    result = [
        ('one', '1', now, 'created', 1),
        ('two', '2', now, 'new release', 2),
        ('one', '2', now_plus_1, 'new release', 3),
        ('one', '3', now_plus_2, 'new release', 4),
    ]
    if not with_ids:
        result = [r[:4] for r in result]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_changelog=pretend.call_recorder(lambda *a: data),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.changelog(old, with_ids) == result

    assert app.models.packaging.get_changelog.calls == [
        pretend.call(old)
    ]


def test_xmlrpc_updated_releases():
    now = datetime.datetime.now()

    result = [
        dict(name='one', version='1', created=now, summary='text'),
        dict(name='two', version='2', created=now, summary='text'),
        dict(name='two', version='3', created=now, summary='text'),
        dict(name='three', version='4', created=now, summary='text')]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_releases_since=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    old = now = datetime.timedelta(days=1)
    assert interface.updated_releases(old) == \
        [('one', '1'), ('two', '2'), ('two', '3'), ('three', '4')]

    assert app.models.packaging.get_releases_since.calls == [
        pretend.call(old)
    ]


def test_xmlrpc_update_releases():
    now = datetime.datetime.now()

    result = [
        dict(name='one', version='1', created=now, summary='text'),
        dict(name='two', version='2', created=now, summary='text'),
        dict(name='two', version='3', created=now, summary='text'),
        dict(name='three', version='4', created=now, summary='text')]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_releases_since=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    old = now = datetime.timedelta(days=1)
    assert interface.updated_releases(old) == \
        [('one', '1'), ('two', '2'), ('two', '3'), ('three', '4')]

    assert app.models.packaging.get_releases_since.calls == [
        pretend.call(old)
    ]


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


def test_release_data(monkeypatch):
    resp = dict(
        name="spam",
        version="1.0",
        author="John Doe",
        author_email="john.doe@example.com",
        maintainer=None,
        maintainer_email=None,
        home_page="https://example.com/",
        license="Apache License v2.0",
        summary="A Test Project",
        description="A Longer Test Project",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        requires_dist=["requests (>=2.0)"],
        provides_dist=["test-project-old"],
        project_url={"Repository": "git://git.example.com/"},
        created=datetime.datetime.utcnow(),
    )
    # snapshot that info now for comparison later
    info = dict(resp)
    docs = "https://pythonhosted.org/spam/"
    cfiers = ['Section A :: Subsection B :: Aisle 3', 'Section B']
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_release=pretend.call_recorder(lambda *a: resp),
                get_documentation_url=pretend.call_recorder(lambda *a: docs),
                get_download_counts=pretend.call_recorder(lambda *a: 10),
                get_classifiers=pretend.call_recorder(lambda *a: cfiers),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    result = interface.release_data('spam', '1.0')

    assert app.models.packaging.get_release.calls == [
        pretend.call('spam', '1.0'),
    ]

    # modify the model response data according to the expected mutation
    info.update(
        package_url='http://pypi.python.org/pypi/spam',
        release_url='http://pypi.python.org/pypi/spam/1.0',
        docs_url=docs,
        downloads=10,
        classifiers=cfiers,
        maintainer='',              # converted from None
        maintainer_email='',        # converted from None
        stable_version='',          # filled in as no-op
    )
    assert result == info


def test_release_data_missing(monkeypatch):
    def f(*a):
        raise IndexError()

    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_release=pretend.call_recorder(f),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    result = interface.release_data('spam', '1.0')

    assert app.models.packaging.get_release.calls == [
        pretend.call('spam', '1.0'),
    ]

    assert result == {}
