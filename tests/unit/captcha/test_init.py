# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.captcha import includeme, interfaces


def test_include_with_custom_backend():
    cache_class = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        registry=pretend.stub(settings={"captcha.backend": "tests.CustomBackend"}),
        maybe_dotted=pretend.call_recorder(lambda n: cache_class),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name: None
        ),
    )
    includeme(config)

    assert config.maybe_dotted.calls == [pretend.call("tests.CustomBackend")]
    assert config.register_service_factory.calls == [
        pretend.call(
            cache_class.create_service,
            interfaces.ICaptchaService,
            name="captcha",
        )
    ]
