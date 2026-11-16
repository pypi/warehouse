# SPDX-License-Identifier: Apache-2.0

import boto3
import pytest

from warehouse import aws


@pytest.mark.parametrize("region", [None, "us-west-2"])
def test_aws_session_factory(mocker, pyramid_request, region):
    boto_session_cls = mocker.patch.object(boto3.session, "Session", autospec=True)
    pyramid_request.registry.settings.update(
        {
            "aws.key_id": "my key",
            "aws.secret_key": "my secret",
        }
    )

    if region is not None:
        pyramid_request.registry.settings["aws.region"] = region

    assert (
        aws.aws_session_factory(None, pyramid_request) is boto_session_cls.return_value
    )
    boto_session_cls.assert_called_once_with(
        aws_access_key_id="my key",
        aws_secret_access_key="my secret",
        **({} if region is None else {"region_name": region}),
    )


def test_includeme(mocker, pyramid_config):
    pyramid_config.include("pyramid_services")
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    aws.includeme(pyramid_config)

    register_service_factory.assert_called_once_with(
        aws.aws_session_factory, name="aws.session"
    )
