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

from warehouse import tasks
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import File, Project, Release


@tasks.task(ignore_result=True, acks_late=True)
def compute_oidc_metrics(request):
    metrics = request.find_service(IMetricsService, context=None)

    projects_configured_oidc = (
        request.db.query(Project.id).distinct().join(Project.oidc_publishers)
    )

    # Metric for count of all projects that have configured OIDC.
    metrics.gauge(
        "warehouse.oidc.total_projects_configured_oidc_publishers",
        projects_configured_oidc.count(),
    )

    # Metric for count of critical projects that have configured OIDC.
    metrics.gauge(
        "warehouse.oidc.total_critical_projects_configured_oidc_publishers",
        projects_configured_oidc.where(Project.pypi_mandates_2fa.is_(True)).count(),
    )

    # Need to check FileEvent.additional['publisher_url'] to determine which
    # projects have successfully published via an OIDC publisher.
    projects_published_with_oidc = (
        request.db.query(Project.id)
        .distinct()
        .join(Project.releases)
        .join(Release.files)
        .join(File.events)
        .where(File.Event.additional.op("->>")("publisher_url").is_not(None))
    )

    # Metric for count of all projects that have published via OIDC
    metrics.gauge(
        "warehouse.oidc.total_projects_published_with_oidc_publishers",
        projects_published_with_oidc.count(),
    )

    # Metric for count of critical projects that have published via OIDC
    metrics.gauge(
        "warehouse.oidc.total_critical_projects_published_with_oidc_publishers",
        projects_published_with_oidc.where(Project.pypi_mandates_2fa.is_(True)).count(),
    )
