# SPDX-License-Identifier: Apache-2.0

from google.cloud import bigquery
from google.cloud.storage import Client as storage_Client


def gcloud_bigquery_factory(context, request):
    service_account_info = request.registry.settings["gcloud.service_account_info"]
    project = request.registry.settings["gcloud.project"]

    return bigquery.Client.from_service_account_info(
        service_account_info, project=project
    )


def gcloud_gcs_factory(context, request):
    service_account_info = request.registry.settings["gcloud.service_account_info"]
    project = request.registry.settings["gcloud.project"]

    return storage_Client.from_service_account_info(
        service_account_info, project=project
    )


def includeme(config):
    config.register_service_factory(gcloud_bigquery_factory, name="gcloud.bigquery")
    config.register_service_factory(gcloud_gcs_factory, name="gcloud.gcs")
