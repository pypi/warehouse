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

import pretend
import pytest

from warehouse.helpers import url_for


@pytest.mark.parametrize(("external",), [(False,), (True,)])
def test_url_for(external):
    request = pretend.stub(
        url_adapter=pretend.stub(
            build=pretend.call_recorder(lambda *a, **k: "/foo/"),
        ),
    )

    assert url_for(
        request,
        "warehouse.test",
        foo="bar",
        _force_external=external,
    ) == "/foo/"

    assert request.url_adapter.build.calls == [
        pretend.call(
            "warehouse.test",
            {"foo": "bar"},
            force_external=external,
        ),
    ]
