# SPDX-License-Identifier: Apache-2.0


def gcloud_bigquery_factory(context, request):
    # Deferred: avoid the import cost when this backend isn't in use
    from google.cloud import bigquery  # noqa: PLC0415

    service_account_info = request.registry.settings["gcloud.service_account_info"]
    project = request.registry.settings["gcloud.project"]

    return bigquery.Client.from_service_account_info(
        service_account_info, project=project
    )


def gcloud_gcs_factory(context, request):
    # Deferred: avoid the import cost when this backend isn't in use
    from google.cloud.storage import Client as storage_Client  # noqa: PLC0415

    service_account_info = request.registry.settings["gcloud.service_account_info"]
    project = request.registry.settings["gcloud.project"]

    return storage_Client.from_service_account_info(
        service_account_info, project=project
    )


def includeme(config):
    config.register_service_factory(gcloud_bigquery_factory, name="gcloud.bigquery")
    config.register_service_factory(gcloud_gcs_factory, name="gcloud.gcs")
