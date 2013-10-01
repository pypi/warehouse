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


from warehouse.http import Response


def test_response_surrogate_control():
    resp = Response()

    assert "Surrogate-Control" not in resp.headers

    resp.surrogate_control.public = True
    resp.surrogate_control.max_age = 120

    assert set(resp.headers["Surrogate-Control"].split(", ")) == {
        "max-age=120",
        "public",
    }


def test_response_surrogate_control_remove():
    resp = Response(headers={"Surrogate-Control": "max-age=120"})

    assert resp.headers["Surrogate-Control"] == "max-age=120"

    resp.surrogate_control.max_age = None

    assert "Surrogate-Control" not in resp.headers
