# SPDX-License-Identifier: Apache-2.0

import boto3
import pretend
import pytest

from warehouse import aws


@pytest.mark.parametrize("region", [None, "us-west-2"])
def test_aws_session_factory(monkeypatch, region):
    boto_session_obj = pretend.stub()
    boto_session_cls = pretend.call_recorder(lambda **kw: boto_session_obj)
    monkeypatch.setattr(boto3.session, "Session", boto_session_cls)

    request = pretend.stub(
        registry=pretend.stub(
            settings={"aws.key_id": "my key", "aws.secret_key": "my secret"}
        )
    )

    if region is not None:
        request.registry.settings["aws.region"] = region

    assert aws.aws_session_factory(None, request) is boto_session_obj
    assert boto_session_cls.calls == [
        pretend.call(
            aws_access_key_id="my key",
            aws_secret_access_key="my secret",
            **({} if region is None else {"region_name": region})
        )
    ]


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda factory, name: None)
    )

    aws.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(aws.aws_session_factory, name="aws.session")
    ]
