# SPDX-License-Identifier: Apache-2.0

from google.cloud import bigquery
from google.cloud.storage import Client as storage_Client

from warehouse import gcloud


def test_gcloud_bigquery_factory(pyramid_request, mocker):
    client = mocker.sentinel.client
    from_service_account_info = mocker.patch.object(
        bigquery.Client,
        "from_service_account_info",
        autospec=True,
        return_value=client,
    )

    pyramid_request.registry.settings.update(
        {
            "gcloud.service_account_info": {},
            "gcloud.project": "my-cool-project",
        }
    )

    assert gcloud.gcloud_bigquery_factory(None, pyramid_request) is client
    from_service_account_info.assert_called_once_with({}, project="my-cool-project")


def test_gcloud_gcs_factory(pyramid_request, mocker):
    client = mocker.sentinel.client
    from_service_account_info = mocker.patch.object(
        storage_Client,
        "from_service_account_info",
        autospec=True,
        return_value=client,
    )

    pyramid_request.registry.settings.update(
        {
            "gcloud.service_account_info": {},
            "gcloud.project": "my-cool-project",
        }
    )

    assert gcloud.gcloud_gcs_factory(None, pyramid_request) is client
    from_service_account_info.assert_called_once_with({}, project="my-cool-project")


def test_includeme(mocker):
    config = mocker.Mock(spec=["register_service_factory"])

    gcloud.includeme(config)

    assert config.register_service_factory.call_args_list == [
        mocker.call(gcloud.gcloud_bigquery_factory, name="gcloud.bigquery"),
        mocker.call(gcloud.gcloud_gcs_factory, name="gcloud.gcs"),
    ]


def test_no_module_level_google_imports():
    """The google.cloud imports should be deferred, not at module level."""
    assert not hasattr(gcloud, "bigquery")
    assert not hasattr(gcloud, "storage_Client")
