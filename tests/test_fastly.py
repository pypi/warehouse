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

import pretend

from warehouse.fastly import FastlyKey, FastlyFormatter


class TestFastlyKey:

    def test_format_keys(self):
        fastly_key = FastlyKey("foo", "foo/{bar}", "foo/{bar!n}")
        assert fastly_key.format_keys(bar="WaT") == [
            "foo",
            "foo/WaT",
            "foo/wat",
        ]

    def test_plain_decorator(self):
        fastly_key = FastlyKey("foo", "foo/{bar}", "foo/{bar!n}")

        @fastly_key
        def tester(app, request, bar=None):
            return pretend.stub(headers={})

        assert (
            tester(None, None, bar="WaT").headers["Surrogate-Key"]
            == "foo foo/WaT foo/wat"
        )

    def test_advanced_decorator(self):
        fastly_key = FastlyKey("foo", "foo/{bar}", "foo/{bar!n}")

        @fastly_key(not_bar="bar")
        def tester(app, request, not_bar=None):
            return pretend.stub(headers={})

        assert (
            tester(None, None, not_bar="WaT").headers["Surrogate-Key"]
            == "foo foo/WaT foo/wat"
        )


def test_fastly_formatter():
    assert FastlyFormatter().format("{0}", "Foo") == "Foo"
    assert FastlyFormatter().format("{0!n}", "Foo") == "foo"
