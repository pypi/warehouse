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
from warehouse.packaging.models import Project


@tasks.task(ignore_result=True, acks_late=True)
def compute_oidc_metrics(request):
    metrics = request.find_service(IMetricsService, context=None)

    projects_using_oidc = (
        request.db.query(Project).distinct().join(Project.oidc_publishers)
    )

    # Metric for count of all projects using OIDC
    metrics.gauge(
        "warehouse.oidc.total_projects_using_oidc_publishers",
        projects_using_oidc.count(),
    )

    # Metric for count of critical projects using OIDC
    metrics.gauge(
        "warehouse.oidc.total_critical_projects_using_oidc_publishers",
        projects_using_oidc.where(Project.pypi_mandates_2fa.is_(True)).count(),
    )
