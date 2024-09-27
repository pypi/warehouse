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

from http import HTTPStatus

from webob.multidict import MultiDict

from ..common.db.accounts import UserFactory


def test_rejects_duplicate_post_keys(webtest, socket_enabled):
    # create a User
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")

    # /login is an unauthenticated endpoint that accepts a POST
    login_page = webtest.get("/account/login/", status=HTTPStatus.OK)

    # Get the CSRF token from the form
    login_form = login_page.forms["login-form"]
    anonymous_csrf_token = login_form["csrf_token"].value

    body = MultiDict()
    body.add("username", user.username)
    body.add("password", "password")
    body.add("csrf_token", anonymous_csrf_token)
    # Add multiple duplicate keys to the POST body, doesn't matter what they are
    body.add("foo", "bar")
    body.add("foo", "baz")

    resp = webtest.post("/account/login/", params=body, status=HTTPStatus.BAD_REQUEST)
    assert "POST body may not contain duplicate keys" in resp.body.decode()
    assert "(URL: 'http://localhost/account/login/')" in resp.body.decode()
