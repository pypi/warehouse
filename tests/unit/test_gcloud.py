# SPDX-License-Identifier: Apache-2.0

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
