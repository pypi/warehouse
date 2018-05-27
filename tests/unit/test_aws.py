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
