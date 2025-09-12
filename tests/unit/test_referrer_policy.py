# SPDX-License-Identifier: Apache-2.0

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
