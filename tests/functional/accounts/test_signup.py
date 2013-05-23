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


@pytest.mark.django_db(transaction=True)
def test_simple_signup(webtest):
    form = webtest.get(reverse("accounts.signup")).form
    form["username"] = "testuser"
    form["email"] = "testuser@example.com"
    form["password"] = "test password!"
    form["confirm_password"] = "test password!"
    response = form.submit()

    assert response.status_code == 303
