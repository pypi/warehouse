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

import textwrap

import pretend
import pytest

from werkzeug.exceptions import NotFound

from warehouse.packaging import views
from warehouse.packaging.views import project_detail


def test_project_detail_missing_project(warehouse_app):
    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project=pretend.call_recorder(lambda proj: None),
        ),
    )

    project_name = "test-project"

    with warehouse_app.test_request_context():
        with pytest.raises(NotFound):
            project_detail(project_name)

    assert warehouse_app.db.packaging.get_project.calls == [
        pretend.call("test-project"),
    ]


def test_project_detail_no_versions(warehouse_app):
    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project=pretend.call_recorder(
                lambda proj: "test-project",
            ),
            get_releases=pretend.call_recorder(lambda proj: []),
        ),
    )

    project_name = "test-project"

    with warehouse_app.test_request_context():
        with pytest.raises(NotFound):
            project_detail(project_name)

    assert warehouse_app.db.packaging.get_project.calls == [
        pretend.call("test-project"),
    ]
    assert warehouse_app.db.packaging.get_releases.calls == [
        pretend.call("test-project"),
    ]


def test_project_detail_redirects(warehouse_app):
    warehouse_app.warehouse_config = pretend.stub(
        cache=pretend.stub(
            browser=False,
            varnish=False,
        ),
    )
    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project=pretend.call_recorder(
                lambda proj: "test-project",
            ),
            get_releases=pretend.call_recorder(
                lambda proj: [{"version": "1.0"}],
            ),
        ),
    )

    project_name = "test-Project"
    normalized = "test-project"

    with warehouse_app.test_request_context():
        resp = project_detail(project_name=project_name)

    assert resp.status_code == 301
    assert resp.headers["Location"] == "/project/test-project/"

    assert resp.headers["Surrogate-Key"] == \
        "project project/{}".format(normalized)

    assert warehouse_app.db.packaging.get_project.calls == [
        pretend.call("test-Project"),
    ]
    assert warehouse_app.db.packaging.get_releases.calls == [
        pretend.call("test-project"),
    ]


def test_project_detail_invalid_version(warehouse_app):
    warehouse_app.warehouse_config = pretend.stub(
        cache=pretend.stub(
            browser=False,
            varnish=False,
        ),
    )
    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project=pretend.call_recorder(
                lambda proj: "test-project",
            ),
            get_releases=pretend.call_recorder(
                lambda proj: [{"version": "1.0"}],
            ),
        ),
    )
    project_name = "test-project"

    with warehouse_app.test_request_context():
        with pytest.raises(NotFound):
            project_detail(project_name, "2.0")

    assert warehouse_app.db.packaging.get_project.calls == [
        pretend.call("test-project"),
    ]
    assert warehouse_app.db.packaging.get_releases.calls == [
        pretend.call("test-project"),
    ]


@pytest.mark.parametrize(("version", "description", "camo"), [
    (
        None,
        textwrap.dedent("""
            Test Project
            ============

            This is a test project
        """),
        None,
    ),
    (
        "1.0",
        textwrap.dedent("""
            Test Project
            ============

            This is a test project
        """),
        None,
    ),
    (None, ".. code-fail::\n    wat", None),
    ("1.0", ".. code-fail::\n    wat", None),
    (None, None, None),
    ("1.0", None, None),
    (
        None,
        textwrap.dedent("""
            Test Project
            ============

            This is a test project
        """),
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
    (
        "1.0",
        textwrap.dedent("""
            Test Project
            ============

            This is a test project
        """),
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
    (
        None,
        ".. code-fail::\n    wat",
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
    (
        "1.0",
        ".. code-fail::\n    wat",
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
    (
        None,
        None,
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
    (
        "1.0",
        None,
        pretend.stub(url="https://camo.example.com/", key="secret key"),
    ),
])
def test_project_detail_valid(
        version, description, camo, warehouse_app, monkeypatch):
    release = {
        "description": description,
    }

    response = pretend.stub(
        headers={}, status_code=200,
        cache_control=pretend.stub(),
        surrogate_control=pretend.stub()
    )
    render_template = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_template", render_template)

    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project=pretend.call_recorder(
                lambda proj: "test-project",
            ),
            get_releases=pretend.call_recorder(
                lambda proj: [{"version": "2.0"}, {"version": "1.0"}],
            ),
            get_release=pretend.call_recorder(
                lambda proj, version: release,
            ),
            get_download_counts=pretend.call_recorder(
                lambda proj: {
                    "last_day": 1,
                    "last_week": 7,
                    "last_month": 30,
                },
            ),
            get_downloads=pretend.call_recorder(lambda proj, ver: []),
            get_classifiers=pretend.call_recorder(lambda proj, ver: []),
            get_documentation_url=pretend.call_recorder(
                lambda proj: None,
            ),
            get_bugtrack_url=pretend.call_recorder(lambda proj: None),
            get_users_for_project=pretend.call_recorder(lambda proj: []),
        ),
    )
    warehouse_app.warehouse_config = pretend.stub(camo=camo)

    project_name = "test-project"
    normalized = "test-project"

    with warehouse_app.test_request_context():
        resp = project_detail(
            project_name=project_name,
            version=version,
        )

    assert resp.status_code == 200

    assert resp.headers["Surrogate-Key"] == \
        "project project/{}".format(normalized)

    assert warehouse_app.db.packaging.get_project.calls == [
        pretend.call("test-project"),
    ]
    assert warehouse_app.db.packaging.get_releases.calls == [
        pretend.call("test-project"),
    ]
    assert warehouse_app.db.packaging.get_users_for_project.calls == [
        pretend.call("test-project"),
    ]
