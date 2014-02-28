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

import time
import datetime

import pretend
import pytest

import jinja2

from werkzeug.exceptions import NotFound, BadRequest
from werkzeug.routing import Map

from warehouse.legacy import pypi, xmlrpc
from warehouse.packaging import urls


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

    xmlrpc_stub = pretend.stub(
        handle_request=pretend.call_recorder(lambda *a: 'success')
    )
    monkeypatch.setattr(pypi, 'xmlrpc', xmlrpc_stub)

    # request for /pypi with no additional request information redirects
    # to site root
    #
    resp = pypi.pypi(app, request)

    assert xmlrpc_stub.handle_request.calls == [pretend.call(app, request)]
    assert resp == 'success'


def test_daytime(monkeypatch):
    app = pretend.stub()
    request = pretend.stub()

    monkeypatch.setattr(time, 'time', lambda: 0)

    resp = pypi.daytime(app, request)

    assert resp.response[0] == '19700101T00:00:00\n'


@pytest.mark.parametrize("callback", [None, 'yes'])
def test_json(monkeypatch, callback):
    get_project = pretend.call_recorder(lambda n: 'spam')
    get_project_versions = pretend.call_recorder(lambda n: ['2.0', '1.0'])
    app = pretend.stub(
        config=pretend.stub(cache=pretend.stub(browser=False, varnish=False)),
        db=pretend.stub(
            packaging=pretend.stub(
                get_project=get_project,
                get_project_versions=get_project_versions,
            )
        )
    )
    request = pretend.stub(args={})
    if callback:
        request.args['callback'] = callback

    release_data = pretend.call_recorder(lambda n, v: dict(some='data'))
    release_urls = pretend.call_recorder(lambda n, v: [dict(
        some='url',
        upload_time=datetime.date(1970, 1, 1)
    )])
    Interface = pretend.call_recorder(lambda a, r: pretend.stub(
        release_data=release_data,
        release_urls=release_urls,
    ))

    monkeypatch.setattr(xmlrpc, 'Interface', Interface)

    resp = pypi.project_json(app, request, project_name='spam')

    assert get_project.calls == [pretend.call('spam')]
    assert get_project_versions.calls == [pretend.call('spam')]
    assert release_data.calls == [pretend.call('spam', '2.0')]
    assert release_urls.calls == [pretend.call('spam', '2.0')]
    expected = '{"info": {"some": "data"}, "urls": [{"some": "url", '\
        '"upload_time": "1970-01-01T00:00:00"}]}'
    if callback:
        expected = '/**/ %s(%s);' % (callback, expected)
    assert resp.data == expected


def test_jsonp_invalid():
    app = pretend.stub()
    request = pretend.stub(args={'callback': 'quite invalid'})
    with pytest.raises(BadRequest):
        pypi.project_json(app, request, project_name='spam')


@pytest.mark.parametrize("project", [None, pretend.stub(name="spam")])
def test_json_missing(monkeypatch, project):
    get_project = pretend.call_recorder(lambda n: project)
    get_project_versions = pretend.call_recorder(lambda n: [])
    app = pretend.stub(
        db=pretend.stub(
            packaging=pretend.stub(
                get_project=get_project,
                get_project_versions=get_project_versions,
            )
        )
    )
    request = pretend.stub(args={})

    with pytest.raises(NotFound):
        pypi.project_json(app, request, project_name='spam')


def test_rss(monkeypatch):
    get_recently_updated = pretend.call_recorder(lambda num=10: [
        dict(name='spam', version='1.0', summary='hai spam', created='now'),
        dict(name='ham', version='2.0', summary='hai ham', created='now'),
        dict(name='spam', version='2.0', summary='hai spam v2', created='now'),
    ])
    template = pretend.stub(
        render=pretend.call_recorder(lambda **ctx: "<xml>dummy</xml>"),
    )
    app = pretend.stub(
        db=pretend.stub(
            packaging=pretend.stub(
                get_recently_updated=get_recently_updated,
            )
        ),
        config=pretend.stub(
            cache=pretend.stub(browser=False, varnish=False),
            site={"url": "http://test.server/", "name": "PyPI"},
        ),
        urls=Map(urls.urls).bind('test.server', '/'),
        templates=pretend.stub(
            get_template=pretend.call_recorder(lambda t: template),
        ),
    )
    request = pretend.stub()

    resp = pypi.rss(app, request)

    assert get_recently_updated.calls == [pretend.call(num=40)]
    assert len(template.render.calls) == 1
    assert template.render.calls[0].kwargs['releases'] == [
        {
            'url': 'http://test.server/project/spam/1.0/',
            'version': u'1.0',
            'name': u'spam',
            'summary': u'hai spam',
            'created': u'now',
        }, {
            'url': 'http://test.server/project/ham/2.0/',
            'version': u'2.0',
            'name': u'ham',
            'summary': u'hai ham',
            'created': u'now',
        }, {
            'url': 'http://test.server/project/spam/2.0/',
            'version': u'2.0',
            'name': u'spam',
            'summary': u'hai spam v2',
            'created': u'now',
        }]
    assert resp.data == "<xml>dummy</xml>"


def test_packages_rss(monkeypatch):
    get_recent_projects = pretend.call_recorder(lambda num=10: [
        dict(name='spam', version='1.0', summary='hai spam', created='now'),
        dict(name='ham', version='2.0', summary='hai ham', created='now'),
        dict(name='eggs', version='21.0', summary='hai eggs!', created='now'),
    ])
    template = pretend.stub(
        render=pretend.call_recorder(lambda **ctx: "<xml>dummy</xml>"),
    )
    app = pretend.stub(
        db=pretend.stub(
            packaging=pretend.stub(
                get_recent_projects=get_recent_projects,
            )
        ),
        config=pretend.stub(
            cache=pretend.stub(browser=False, varnish=False),
            site={"url": "http://test.server/", "name": "PyPI"},
        ),
        urls=Map(urls.urls).bind('test.server', '/'),
        templates=pretend.stub(
            get_template=pretend.call_recorder(lambda t: template),
        ),
    )
    request = pretend.stub()

    resp = pypi.packages_rss(app, request)

    assert get_recent_projects.calls == [pretend.call(num=40)]
    assert len(template.render.calls) == 1
    assert template.render.calls[0].kwargs['releases'] == [
        {
            'url': 'http://test.server/project/spam/',
            'version': u'1.0',
            'name': u'spam',
            'summary': u'hai spam',
            'created': u'now',
        }, {
            'url': 'http://test.server/project/ham/',
            'version': u'2.0',
            'name': u'ham',
            'summary': u'hai ham',
            'created': u'now',
        }, {
            'url': 'http://test.server/project/eggs/',
            'version': u'21.0',
            'name': u'eggs',
            'summary': u'hai eggs!',
            'created': u'now',
        }]
    assert resp.data == "<xml>dummy</xml>"


def test_rss_xml_template(monkeypatch):
    templates = jinja2.Environment(
        autoescape=True,
        auto_reload=False,
        extensions=[
            "jinja2.ext.i18n",
        ],
        loader=jinja2.PackageLoader("warehouse"),
    )
    template = templates.get_template('legacy/rss.xml')
    content = template.render(
        site=dict(url='http://test.server/', name="PyPI"),
        description='package updates',
        releases=[
            {
                'url': 'http://test.server/project/spam/',
                'version': u'1.0',
                'name': u'spam',
                'summary': u'hai spam',
                'created': datetime.date(1970, 1, 1),
            }, {
                'url': 'http://test.server/project/ham/',
                'version': u'2.0',
                'name': u'ham',
                'summary': u'hai ham',
                'created': datetime.date(1970, 1, 1),
            }, {
                'url': 'http://test.server/project/eggs/',
                'version': u'21.0',
                'name': u'eggs',
                'summary': u'hai eggs!',
                'created': datetime.date(1970, 1, 1),
            }
        ],
    )
    assert content == '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE rss PUBLIC "-//Netscape Communications//DTD RSS 0.91//EN" \
"http://my.netscape.com/publish/formats/rss-0.91.dtd">
<rss version="0.91">
 <channel>
  <title>PyPI Recent Package Updates</title>
  <link>http://test.server/</link>
  <description>Recent package updates at PyPI</description>
  <language>en</language>
  \n\
  <item>
    <title>spam 1.0</title>
    <link>http://test.server/project/spam/</link>
    <guid>http://test.server/project/spam/</guid>
    <description>hai spam</description>
    <pubDate>01 Jan 1970 00:00:00 GMT</pubDate>
  </item>
  \n\
  <item>
    <title>ham 2.0</title>
    <link>http://test.server/project/ham/</link>
    <guid>http://test.server/project/ham/</guid>
    <description>hai ham</description>
    <pubDate>01 Jan 1970 00:00:00 GMT</pubDate>
  </item>
  \n\
  <item>
    <title>eggs 21.0</title>
    <link>http://test.server/project/eggs/</link>
    <guid>http://test.server/project/eggs/</guid>
    <description>hai eggs!</description>
    <pubDate>01 Jan 1970 00:00:00 GMT</pubDate>
  </item>
  \n\
  </channel>
</rss>'''
