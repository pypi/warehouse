# SPDX-License-Identifier: Apache-2.0

import b2sdk.v2

from warehouse import b2


def test_b2_api_factory(mocker, pyramid_request):
    account_info_cls = mocker.patch.object(
        b2sdk.v2, "InMemoryAccountInfo", autospec=True
    )
    b2_api_cls = mocker.patch.object(b2sdk.v2, "B2Api", autospec=True)
    pyramid_request.registry.settings.update(
        {
            "b2.application_key_id": "key_id",
            "b2.application_key": "key",
        }
    )

    b2_api = b2.b2_api_factory(None, pyramid_request)

    assert b2_api is b2_api_cls.return_value
    account_info_cls.assert_called_once_with()
    b2_api_cls.assert_called_once_with(account_info_cls.return_value)
    b2_api.authorize_account.assert_called_once_with("production", "key_id", "key")


def test_includeme(mocker, pyramid_config):
    pyramid_config.include("pyramid_services")
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    b2.includeme(pyramid_config)

    register_service_factory.assert_called_once_with(b2.b2_api_factory, name="b2.api")
