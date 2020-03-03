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

from google.cloud import bigquery, storage


def gcloud_bigquery_factory(context, request):
    credentials = request.registry.settings["gcloud.credentials"]
    project = request.registry.settings["gcloud.project"]

    return bigquery.Client.from_service_account_json(credentials, project=project)


def gcloud_gcs_factory(context, request):
    credentials = request.registry.settings["gcloud.credentials"]
    project = request.registry.settings["gcloud.project"]

    return storage.Client.from_service_account_json(credentials, project=project)


def includeme(config):
    config.register_service_factory(gcloud_bigquery_factory, name="gcloud.bigquery")
    config.register_service_factory(gcloud_gcs_factory, name="gcloud.gcs")
