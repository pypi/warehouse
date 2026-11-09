# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.captcha import hcaptcha, includeme, interfaces, recaptcha


@pytest.mark.parametrize(
    ("backend", "service_class"),
    [
        ("warehouse.captcha.hcaptcha.Service", hcaptcha.Service),
        ("warehouse.captcha.recaptcha.Service", recaptcha.Service),
    ],
)
def test_includeme(pyramid_config, mocker, backend, service_class):
    pyramid_config.include("pyramid_services")
    pyramid_config.registry.settings["captcha.backend"] = backend
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    includeme(pyramid_config)

    register_service_factory.assert_called_once_with(
        service_class.create_service,
        interfaces.ICaptchaService,
        name="captcha",
    )
