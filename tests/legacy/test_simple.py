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

import os.path

import pretend
import pytest

from werkzeug.datastructures import Headers
from werkzeug.exceptions import NotFound
from werkzeug.test import create_environ

from warehouse.packaging.models import Project
from warehouse.legacy import simple


def test_index(monkeypatch):
    response = pretend.stub(status_code=200, headers=Headers())
    render = pretend.call_recorder(lambda *a, **k: response)
    monkeypatch.setattr(simple, "render_response", render)

    all_projects = [Project("bar"), Project("foo")]

    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(browser=False, varnish=False),
        ),
        models=pretend.stub(
            packaging=pretend.stub(
                all_projects=pretend.call_recorder(lambda: all_projects),
                get_last_serial=pretend.call_recorder(lambda: 9999),
            ),
        ),
    )
    request = pretend.stub()

    resp = simple.index(app, request)

    assert resp is response
    assert resp.headers["X-PyPI-Last-Serial"] == "9999"
    assert resp.headers["Surrogate-Key"] == "simple-index"

    assert render.calls == [
        pretend.call(
            app, request,
            "legacy/simple/index.html",
            projects=all_projects,
        ),
    ]


@pytest.mark.parametrize(
    ("project_name", "hosting_mode", "release_urls", "e_project_urls"),
    [
        ("foo", "pypi-explicit", {}, []),
        ("foo", "pypi-explicit", {}, []),
        (
            "foo", "pypi-scrape",
            {
                "1.0": (
                    "http://example.com/home/",
                    "http://example.com/download/",
                ),
            },
            [
                {
                    "name": "1.0 home_page",
                    "rel": "ext-homepage",
                    "url": "http://example.com/home/",
                },
                {
                    "name": "1.0 download_url",
                    "rel": "ext-download",
                    "url": "http://example.com/download/",
                },
            ],
        ),
        ("foo", "pypi-scrape", {"1.0": ("UNKNOWN", "UNKNOWN")}, []),
    ],
)
def test_project(project_name, hosting_mode, release_urls,
        e_project_urls, monkeypatch):
    response = pretend.stub(status_code=200, headers=Headers())
    render = pretend.call_recorder(lambda *a, **k: response)
    url_for = lambda *a, **k: "/foo/"

    monkeypatch.setattr(simple, "render_response", render)
    monkeypatch.setattr(simple, "url_for", url_for)

    project = Project(project_name)

    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(browser=False, varnish=False),
        ),
        models=pretend.stub(
            packaging=pretend.stub(
                get_project=pretend.call_recorder(lambda p: project),
                get_file_urls=pretend.call_recorder(lambda p: []),
                get_hosting_mode=pretend.call_recorder(
                    lambda p: hosting_mode,
                ),
                get_external_urls=pretend.call_recorder(lambda p: []),
                get_last_serial=pretend.call_recorder(lambda p: 9999),
                get_release_urls=pretend.call_recorder(lambda p: release_urls),
            ),
        ),
    )
    request = pretend.stub()

    resp = simple.project(app, request, project_name=project_name)

    assert resp is response
    assert resp.headers["Link"] == "</foo/>; rel=canonical"
    assert (resp.headers["Surrogate-Key"] ==
        "simple simple~{}".format(project_name))

    assert render.calls == [
        pretend.call(
            app, request, "legacy/simple/detail.html",
            project=project,
            project_urls=e_project_urls,
            files=[],
            external_urls=[],
        ),
    ]
    assert app.models.packaging.get_project.calls == [
        pretend.call(project_name),
    ]
    assert app.models.packaging.get_file_urls.calls == [
        pretend.call(project_name),
    ]
    assert app.models.packaging.get_hosting_mode.calls == [
        pretend.call(project_name),
    ]
    assert app.models.packaging.get_external_urls.calls == [
        pretend.call(project_name),
    ]
    assert app.models.packaging.get_last_serial.calls == [
        pretend.call(project_name),
    ]

    if hosting_mode == "pypi-explicit":
        assert app.models.packaging.get_release_urls.calls == []
    else:
        assert app.models.packaging.get_release_urls.calls == [
            pretend.call(project_name),
        ]


def test_project_not_found():
    app = pretend.stub(
        models=pretend.stub(
            packaging=pretend.stub(
                get_project=pretend.call_recorder(lambda p: None),
            ),
        ),
    )
    request = pretend.stub()

    with pytest.raises(NotFound):
        simple.project(app, request, project_name="foo")

    assert app.models.packaging.get_project.calls == [pretend.call("foo")]


@pytest.mark.parametrize(("serial", "md5_hash"), [
    (999, "d41d8cd98f00b204e9800998ecf8427f"),
    (None, "d41d8cd98f00b204e9800998ecf8427f"),
    (999, None),
    (None, None),
])
def test_package(serial, md5_hash, monkeypatch):
    safe_join = pretend.call_recorder(
        lambda *a, **k: "/tmp/packages/any/t/test-1.0.tar.gz"
    )
    _fp = pretend.stub(__enter__=lambda: None, __exit__=lambda *a: None)
    _open = pretend.call_recorder(lambda *a, **k: _fp)
    wrap_file = lambda *a, **k: None
    mtime = pretend.call_recorder(lambda f: 123457)
    getsize = pretend.call_recorder(lambda f: 54321)

    monkeypatch.setattr(simple, "safe_join", safe_join)
    monkeypatch.setattr(simple, "open", _open, raising=False)
    monkeypatch.setattr(simple, "wrap_file", wrap_file)
    monkeypatch.setattr(os.path, "getmtime", mtime)
    monkeypatch.setattr(os.path, "getsize", getsize)

    gpff = pretend.call_recorder(lambda p: Project("test"))
    get_md5 = pretend.call_recorder(
        lambda p: md5_hash
    )
    get_last_serial = pretend.call_recorder(lambda p: serial)

    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(browser=False, varnish=False),
            paths=pretend.stub(packages="/tmp"),
        ),
        models=pretend.stub(
            packaging=pretend.stub(
                get_project_for_filename=gpff,
                get_filename_md5=get_md5,
                get_last_serial=get_last_serial,
            ),
        ),
    )
    request = pretend.stub(environ=create_environ())

    resp = simple.package(app, request, path="packages/any/t/test-1.0.tar.gz")

    if serial:
        assert resp.headers["X-PyPI-Last-Serial"] == str(serial)
    else:
        assert "X-PyPI-Last-Serial" not in resp.headers

    assert resp.headers["Surrogate-Key"] == "package package~test"
    assert resp.headers["Content-Length"] == "54321"

    assert safe_join.calls == [
        pretend.call("/tmp", "packages/any/t/test-1.0.tar.gz"),
    ]
    assert _open.calls == [
        pretend.call("/tmp/packages/any/t/test-1.0.tar.gz", "rb"),
    ]
    assert mtime.calls == [pretend.call("/tmp/packages/any/t/test-1.0.tar.gz")]
    assert getsize.calls == [
        pretend.call("/tmp/packages/any/t/test-1.0.tar.gz"),
    ]
    assert gpff.calls == [pretend.call("test-1.0.tar.gz")]
    assert get_md5.calls == [pretend.call("test-1.0.tar.gz")]
    assert get_last_serial.calls == [pretend.call("test")]


def test_package_not_found_unsafe(monkeypatch):
    safe_join = pretend.call_recorder(lambda *a, **k: None)
    monkeypatch.setattr(simple, "safe_join", safe_join)

    app = pretend.stub(
        config=pretend.stub(
            paths=pretend.stub(packages="/tmp"),
        ),
    )
    request = pretend.stub()

    with pytest.raises(NotFound):
        simple.package(app, request, path="packages/any/t/test-1.0.tar.gz")

    assert safe_join.calls == [
        pretend.call("/tmp", "packages/any/t/test-1.0.tar.gz"),
    ]


def test_package_not_found_unsafe_missing(monkeypatch):
    safe_join = pretend.call_recorder(
        lambda *a, **k: "/tmp/packages/any/t/test-1.0.tar.gz"
    )

    def raising_open(*args, **kwargs):
        raise IOError

    _open = pretend.call_recorder(raising_open)

    monkeypatch.setattr(simple, "safe_join", safe_join)
    monkeypatch.setattr(simple, "open", _open, raising=False)

    app = pretend.stub(
        config=pretend.stub(
            paths=pretend.stub(packages="/tmp"),
        ),
    )
    request = pretend.stub()

    with pytest.raises(NotFound):
        simple.package(app, request, path="packages/any/t/test-1.0.tar.gz")

    assert safe_join.calls == [
        pretend.call("/tmp", "packages/any/t/test-1.0.tar.gz"),
    ]
    assert _open.calls == [
        pretend.call("/tmp/packages/any/t/test-1.0.tar.gz", "rb"),
    ]
