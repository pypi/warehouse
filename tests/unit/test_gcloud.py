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

from warehouse import gcloud


def test_gcloud_bigquery_factory(monkeypatch):
    client = pretend.stub()

    bigquery = pretend.stub(
        Client=pretend.stub(
            from_service_account_info=pretend.call_recorder(
                lambda account_info, project: client
            )
        )
    )
    monkeypatch.setattr(gcloud, "bigquery", bigquery)

    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "gcloud.service_account_info": {},
                "gcloud.project": "my-cool-project",
            }
        )
    )

    assert gcloud.gcloud_bigquery_factory(None, request) is client
    assert bigquery.Client.from_service_account_info.calls == [
        pretend.call({}, project="my-cool-project")
    ]


def test_gcloud_gcs_factory(monkeypatch):
    client = pretend.stub()

    storage_client = pretend.stub(
        from_service_account_info=pretend.call_recorder(
            lambda account_info, project: client
        )
    )
    monkeypatch.setattr(gcloud, "storage_Client", storage_client)

    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "gcloud.service_account_info": {},
                "gcloud.project": "my-cool-project",
            }
        )
    )

    assert gcloud.gcloud_gcs_factory(None, request) is client
    assert storage_client.from_service_account_info.calls == [
        pretend.call({}, project="my-cool-project")
    ]


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda factory, name: None)
    )

    gcloud.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(gcloud.gcloud_bigquery_factory, name="gcloud.bigquery"),
        pretend.call(gcloud.gcloud_gcs_factory, name="gcloud.gcs"),
    ]
