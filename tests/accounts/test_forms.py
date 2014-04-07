# Copyright 2014 Donald Stufft
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
from werkzeug.datastructures import MultiDict

from warehouse.accounts.forms import LoginForm


def test_validate_username_valid():
    form = LoginForm(
        MultiDict({"username": "test-user", "password": "p@ssw0rd"}),
        authenticator=lambda username, password: True,
    )
    assert form.validate()


def test_validate_username_invalid():
    form = LoginForm(
        MultiDict({"username": "test-user", "password": "p@ssw0rd"}),
        authenticator=lambda username, password: False,
    )
    assert not form.validate()
