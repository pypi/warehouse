# SPDX-License-Identifier: Apache-2.0

import types

from warehouse import referrer_policy


class TestReferrerPolicyTween:
    def test_referrer_policy(self, mocker):
        response = types.SimpleNamespace(headers={})
        handler = mocker.Mock(return_value=response)
        registry = mocker.sentinel.registry
        tween = referrer_policy.referrer_policy_tween_factory(handler, registry)

        request = types.SimpleNamespace(path="/project/foobar/")

        assert tween(request) is response
        assert response.headers == {"Referrer-Policy": "origin-when-cross-origin"}


def test_includeme(pyramid_config, mocker):
    spy = mocker.spy(pyramid_config, "add_tween")
    referrer_policy.includeme(pyramid_config)

    spy.assert_called_once_with(
        "warehouse.referrer_policy.referrer_policy_tween_factory"
    )
