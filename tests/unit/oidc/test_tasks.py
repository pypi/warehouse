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

from warehouse.oidc.tasks import compute_oidc_metrics

from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import ProjectFactory


def test_compute_oidc_metrics(db_request, metrics):
    # Projects with OIDC
    critical_project_oidc = ProjectFactory.create(
        name="critical_project_oidc", pypi_mandates_2fa=True
    )
    non_critical_project_oidc = ProjectFactory.create(
        name="non_critical_project_oidc",
    )

    # Projects without OIDC
    critical_project_no_oidc = ProjectFactory.create(
        name="critical_project_no_oidc", pypi_mandates_2fa=True
    )
    non_critical_project_no_oidc = ProjectFactory.create(
        name="non_critical_project_no_oidc",
    )

    # Create OIDC publishers. One OIDCPublisher can be shared by multiple
    # projects so 'oidc_publisher_1' represents that situation. Verify
    # that metrics don't double-count projects using multiple OIDC publishers.
    oidc_publisher_1 = GitHubPublisherFactory.create(
        projects=[critical_project_oidc, non_critical_project_oidc]
    )
    oidc_publisher_2 = GitHubPublisherFactory.create(projects=[critical_project_oidc])

    compute_oidc_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.total_projects_using_oidc_publishers", 2),
        pretend.call("warehouse.oidc.total_critical_projects_using_oidc_publishers", 1),
    ]
