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

import b2sdk.v2
import pretend

from warehouse import b2


def test_b2_api_factory(monkeypatch):
    mock_in_memory_account_info = pretend.call_recorder(lambda: "InMemoryAccountInfo")
    monkeypatch.setattr(b2sdk.v2, "InMemoryAccountInfo", mock_in_memory_account_info)
    mock_b2_api = pretend.stub(
        authorize_account=pretend.call_recorder(lambda mode, key_id, key: None)
    )
    mock_b2_api_class = pretend.call_recorder(lambda account_info: mock_b2_api)
    monkeypatch.setattr(b2sdk.v2, "B2Api", mock_b2_api_class)

    request = pretend.stub(
        registry=pretend.stub(
            settings={"b2.application_key_id": "key_id", "b2.application_key": "key"}
        )
    )

    assert b2.b2_api_factory(None, request) is mock_b2_api
    assert mock_b2_api_class.calls == [pretend.call("InMemoryAccountInfo")]
    assert mock_b2_api.authorize_account.calls == [
        pretend.call("production", "key_id", "key")
    ]


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda factory, name: None)
    )

    b2.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(b2.b2_api_factory, name="b2.api")
    ]
