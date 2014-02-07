# -*- encoding: utf8 -*-
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

import datetime

import arrow
import pretend
import pytest

from werkzeug.exceptions import BadRequest

from warehouse.legacy import xmlrpc


def test_xmlrpc_handler(monkeypatch):
    Response = pretend.call_recorder(lambda *a, **k: 'response')
    monkeypatch.setattr(xmlrpc, "Response", Response)

    # I'm aware that list_packages shouldn't return data with unicode strings
    # but for the purposes of this test I'm just ensuring that unicode data is
    # handled sanely
    interface = pretend.stub(
        list_packages=pretend.call_recorder(lambda *a, **k: ['one', 'unicod€'])
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
    assert response_xml == '''<?xml version='1.0'?>
<methodResponse>
<params>
<param>
<value><array><data>
<value><string>one</string></value>
<value><string>unicod\xe2\x82\xac</string></value>
</data></array></value>
</param>
</params>
</methodResponse>
'''

    assert Response.calls[0].kwargs == dict(mimetype='text/xml; charset=utf-8')


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
    all_projects = ["bar", "foo"]

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


def test_xmlrpc_package_roles():
    result = [
        dict(user_name='one', role_name='Owner'),
        dict(user_name='two', role_name='Maintainer')
    ]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_roles_for_project=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.package_roles('name') == [
        ['one', 'Owner'], ['two', 'Maintainer']
    ]

    assert app.models.packaging.get_roles_for_project.calls == [
        pretend.call('name')
    ]


def test_xmlrpc_user_packages():
    result = [
        dict(package_name='one', role_name='Owner'),
        dict(package_name='two', role_name='Maintainer')
    ]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_roles_for_user=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.user_packages('name') == [
        ['one', 'Owner'], ['two', 'Maintainer']
    ]

    assert app.models.packaging.get_roles_for_user.calls == [
        pretend.call('name')
    ]


def test_xmlrpc_package_hosting_mode():
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_hosting_mode=pretend.call_recorder(lambda *a: 'yes!'),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.package_hosting_mode('name') == 'yes!'

    assert app.models.packaging.get_hosting_mode.calls == [
        pretend.call('name')
    ]


def test_xmlrpc_release_downloads():
    results = [
        dict(filename='one', downloads=1),
        dict(filename='two', downloads=2),
    ]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_downloads=pretend.call_recorder(lambda *a: results),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.release_downloads('name', '1.0') == [
        ['one', 1], ['two', 2]
    ]

    assert app.models.packaging.get_downloads.calls == [
        pretend.call('name', '1.0')
    ]


@pytest.mark.parametrize("with_ids", [False, True])
def test_xmlrpc_changelog(with_ids):
    now_timestamp = arrow.utcnow().timestamp
    now = arrow.get(now_timestamp).datetime
    old = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    old_timestamp = arrow.get(old).timestamp
    old = arrow.get(old_timestamp).datetime
    now_plus_1 = now + datetime.timedelta(days=1)
    now_plus_2 = now + datetime.timedelta(days=2)
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
        ['one', '1', arrow.get(now).timestamp, 'created', 1],
        ['two', '2', arrow.get(now).timestamp, 'new release', 2],
        ['one', '2', arrow.get(now_plus_1).timestamp, 'new release', 3],
        ['one', '3', arrow.get(now_plus_2).timestamp, 'new release', 4],
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

    old_timestamp = arrow.get(old).timestamp
    assert interface.changelog(old_timestamp, with_ids) == result

    old = arrow.get(old_timestamp).datetime
    assert app.models.packaging.get_changelog.calls == [
        pretend.call(old)
    ]


def test_xmlrpc_changelog_last_serial():
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_last_changelog_serial=pretend.call_recorder(lambda *a: 2),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.changelog_last_serial() == 2

    assert app.models.packaging.get_last_changelog_serial.calls == [
        pretend.call()
    ]


def test_xmlrpc_changelog_serial():
    now_timestamp = arrow.utcnow().timestamp
    now = arrow.get(now_timestamp).datetime
    now_plus_1 = now + datetime.timedelta(days=1)
    now_plus_2 = now + datetime.timedelta(days=2)
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
        ['one', '1', arrow.get(now).timestamp, 'created', 1],
        ['two', '2', arrow.get(now).timestamp, 'new release', 2],
        ['one', '2', arrow.get(now_plus_1).timestamp, 'new release', 3],
        ['one', '3', arrow.get(now_plus_2).timestamp, 'new release', 4],
    ]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_changelog_serial=pretend.call_recorder(lambda *a: data),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.changelog_since_serial(1) == result

    assert app.models.packaging.get_changelog_serial.calls == [
        pretend.call(1)
    ]


def test_xmlrpc_updated_releases():
    now = datetime.datetime.utcnow()

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

    old_timestamp = arrow.get(now - datetime.timedelta(days=1)).timestamp
    assert interface.updated_releases(old_timestamp) == \
        [['one', '1'], ['two', '2'], ['two', '3'], ['three', '4']]

    assert app.models.packaging.get_releases_since.calls == [
        pretend.call(arrow.get(old_timestamp).datetime)
    ]


def test_xmlrpc_changed_packages():
    now = datetime.datetime.utcnow()

    result = ['one', 'two', 'three']
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_changed_since=pretend.call_recorder(lambda *a: result),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    old_timestamp = arrow.get(now - datetime.timedelta(days=1)).timestamp
    assert interface.changed_packages(old_timestamp) == result

    assert app.models.packaging.get_changed_since.calls == [
        pretend.call(arrow.get(old_timestamp).datetime)
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
    # arrow conversion is messy, make sure we are comparing the same thing
    now_timestamp = arrow.utcnow().timestamp
    now = arrow.get(now_timestamp).datetime

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
        description="A Longer Test Project and let's have some üñìçøđé",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        requires_dist=["requests (>=2.0)"],
        provides_dist=["test-project-old"],
        project_url={"Repository": "git://git.example.com/"},
        created=now,
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
        created=now_timestamp,
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


def test_xmlrpc_browse():
    cids = {'hello': 1, 'there': 2}
    results = [['one', 1], ['two', 2]]
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_classifier_ids=pretend.call_recorder(lambda *a: cids),
                search_by_classifier=pretend.call_recorder(lambda *a: results),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    assert interface.browse(['hello', 'there']) == results

    assert app.models.packaging.get_classifier_ids.calls == [
        pretend.call(['hello', 'there'])
    ]
    assert app.models.packaging.search_by_classifier.calls == [
        pretend.call([2, 1])
    ]


def test_xmlrpc_browse_invalid_arg():
    interface = xmlrpc.Interface(pretend.stub(), pretend.stub())

    with pytest.raises(TypeError):
        interface.browse('hello')


def test_xmlrpc_browse_invalid_classifier():
    cids = {'hello': 1}
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_classifier_ids=pretend.call_recorder(lambda *a: cids),
            ),
        ),
    )

    interface = xmlrpc.Interface(app, pretend.stub())

    with pytest.raises(ValueError):
        interface.browse(['hello', 'spam'])
