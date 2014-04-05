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

import pretend
import pytest

from werkzeug.exceptions import NotFound

from warehouse.accounts.views import user_profile


def test_user_profile_missing_user():
    app = pretend.stub(
        db=pretend.stub(
            accounts=pretend.stub(
                get_user=pretend.call_recorder(lambda user: None),
            ),
        ),
    )
    request = pretend.stub()

    username = "test-user"

    with pytest.raises(NotFound):
        user_profile(app, request, username=username)

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]


def test_user_profile_redirects():
    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(
                browser=False,
                varnish=False,
            ),
        ),
        db=pretend.stub(
            accounts=pretend.stub(
                get_user=pretend.call_recorder(
                    lambda user: {"username": "test-User"},
                ),
            ),
        ),
    )
    request = pretend.stub(
        url_adapter=pretend.stub(
            build=pretend.call_recorder(
                lambda *a, **kw: "/~test-User/",
            ),
        ),
    )

    username = "test-user"

    resp = user_profile(app, request, username=username)

    assert resp.status_code == 301
    assert resp.headers["Location"] == "/~test-User/"

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]

    assert request.url_adapter.build.calls == [
        pretend.call(
            "warehouse.accounts.views.user_profile",
            {"username": "test-User"},
            force_external=False,
        ),
    ]


def test_user_profile_renders():
    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(
                browser=False,
                varnish=False,
            ),
        ),
        db=pretend.stub(
            accounts=pretend.stub(
                get_user=pretend.call_recorder(
                    lambda user: {"username": "test-user"},
                ),
            ),
            packaging=pretend.stub(
                get_projects_for_user=pretend.call_recorder(
                    lambda user: None,
                ),
            ),
        ),
        templates=pretend.stub(
            get_template=pretend.call_recorder(
                lambda t: pretend.stub(render=lambda **ctx: ""),
            ),
        ),
    )
    request = pretend.stub()

    username = "test-user"

    resp = user_profile(app, request, username=username)

    assert resp.status_code == 200

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]
    assert app.db.packaging.get_projects_for_user.calls == [
        pretend.call("test-user"),
    ]

    assert app.templates.get_template.calls == [
        pretend.call("accounts/profile.html"),
    ]
