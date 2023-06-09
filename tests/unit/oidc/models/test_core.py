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

from warehouse.oidc.models import _core


def test_check_claim_binary():
    wrapped = _core.check_claim_binary(str.__eq__)

    assert wrapped("foo", "bar", pretend.stub()) is False
    assert wrapped("foo", "foo", pretend.stub()) is True


def test_check_claim_invariant():
    wrapped = _core.check_claim_invariant(True)
    assert wrapped(True, True, pretend.stub()) is True
    assert wrapped(False, True, pretend.stub()) is False

    wrapped = _core.check_claim_invariant(False)
    assert wrapped(False, False, pretend.stub()) is True
    assert wrapped(True, False, pretend.stub()) is False

    identity = object()
    wrapped = _core.check_claim_invariant(identity)
    assert wrapped(object(), object(), pretend.stub()) is False
    assert wrapped(identity, object(), pretend.stub()) is False
    assert wrapped(object(), identity, pretend.stub()) is False
    assert wrapped(identity, identity, pretend.stub()) is True


class TestOIDCPublisher:
    def test_lookup_by_claims_default_none(self):
        assert (
            _core.OIDCPublisher.lookup_by_claims(pretend.stub(), pretend.stub()) is None
        )

    def test_oidc_publisher_not_default_verifiable(self):
        publisher = _core.OIDCPublisher(projects=[])

        assert not publisher.verify_claims(signed_claims={})
