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

from warehouse.domain import DomainPredicate, includeme


class TestDomainPredicate:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, "domain = None"), ("pypi.io", "domain = {!r}".format("pypi.io"))],
    )
    def test_text(self, value, expected):
        predicate = DomainPredicate(value, None)
        assert predicate.text() == expected
        assert predicate.phash() == expected

    def test_when_not_set(self):
        predicate = DomainPredicate(None, None)
        assert predicate(None, None)

    def test_valid_value(self):
        predicate = DomainPredicate("upload.pypi.io", None)
        assert predicate(None, pretend.stub(domain="upload.pypi.io"))

    def test_invalid_value(self):
        predicate = DomainPredicate("upload.pyp.io", None)
        assert not predicate(None, pretend.stub(domain="pypi.io"))


def test_includeme():
    config = pretend.stub(
        add_route_predicate=pretend.call_recorder(lambda name, pred: None)
    )
    includeme(config)

    assert config.add_route_predicate.calls == [pretend.call("domain", DomainPredicate)]
