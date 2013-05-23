# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pytest

from django.core.urlresolvers import reverse

from warehouse.accounts.models import User


@pytest.mark.django_db(transaction=True)
def test_login_valid(webtest):
    User.objects.create_user(username="testuser", password="test password!")

    form = webtest.get(reverse("accounts.login")).form
    form["username"] = "testuser"
    form["password"] = "test password!"
    response = form.submit()

    assert response.status_code == 303


@pytest.mark.django_db(transaction=True)
def test_login_valid_with_next(webtest):
    User.objects.create_user(username="testuser", password="test password!")

    form = webtest.get(reverse("accounts.login") + "?next=/").form
    form["username"] = "testuser"
    form["password"] = "test password!"
    response = form.submit()

    assert response.status_code == 303
    assert response["Location"] == "http://testserver/"


@pytest.mark.django_db(transaction=True)
def test_login_invalid_user(webtest):
    form = webtest.get(reverse("accounts.login") + "?next=/").form
    form["username"] = "testuser"
    form["password"] = "test password!"
    response = form.submit()

    pq = response.pyquery
    assert response.status_code == 200
    assert pq("div.alert")[0].text == "Invalid username or password"


@pytest.mark.django_db(transaction=True)
def test_login_inactive_user(webtest):
    u = User.objects.create_user(username="testuser", password="password!")
    u.is_active = False
    u.save()

    form = webtest.get(reverse("accounts.login") + "?next=/").form
    form["username"] = "testuser"
    form["password"] = "password!"
    response = form.submit()

    pq = response.pyquery
    assert response.status_code == 200
    assert pq("div.alert")[0].text == ("This account is inactive or has been "
                                        "locked by an administrator.")


@pytest.mark.django_db(transaction=True)
def test_login_already_logged_in(webtest):
    response = webtest.get(reverse("accounts.login"), user="testuser")
    assert response.status_code == 303
