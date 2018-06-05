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

from warehouse import referrer_policy


class TestReferrerPolicyTween:
    def test_referrer_policy(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub()
        tween = referrer_policy.referrer_policy_tween_factory(handler, registry)

        request = pretend.stub(path="/project/foobar/")

        assert tween(request) is response
        assert response.headers == {"Referrer-Policy": "origin-when-cross-origin"}


def test_includeme():
    config = pretend.stub(add_tween=pretend.call_recorder(lambda tween: None))
    referrer_policy.includeme(config)

    assert config.add_tween.calls == [
        pretend.call("warehouse.referrer_policy.referrer_policy_tween_factory")
    ]
