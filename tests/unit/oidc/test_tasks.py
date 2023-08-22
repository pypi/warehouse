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

import datetime

import pretend

from warehouse.oidc.tasks import compute_oidc_metrics

from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import (
    FileEventFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
)


def test_compute_oidc_metrics(db_request, metrics):
    # Projects with OIDC
    critical_project_oidc = ProjectFactory.create(
        name="critical_project_oidc", pypi_mandates_2fa=True
    )
    non_critical_project_oidc = ProjectFactory.create(
        name="non_critical_project_oidc",
    )
    non_released_critical_project_oidc = ProjectFactory.create(
        name="non_released_critical_project_oidc", pypi_mandates_2fa=True
    )
    non_released_project_oidc = ProjectFactory.create(
        name="non_released_project_oidc",
    )

    # Projects without OIDC
    ProjectFactory.create(name="critical_project_no_oidc", pypi_mandates_2fa=True)
    ProjectFactory.create(
        name="non_critical_project_no_oidc",
    )

    # Create an OIDC publisher that's shared by multiple projects.
    GitHubPublisherFactory.create(
        projects=[critical_project_oidc, non_critical_project_oidc]
    )

    # Create an OIDC publisher that is only used by one project.
    GitHubPublisherFactory.create(projects=[critical_project_oidc])

    # Create OIDC publishers for projects which have no releases.
    GitHubPublisherFactory.create(projects=[non_released_critical_project_oidc])
    GitHubPublisherFactory.create(projects=[non_released_project_oidc])

    # Create some files which have/have not been published
    # using OIDC in different scenarios.

    # Scenario: Same release, difference between files.
    release_1 = ReleaseFactory.create(project=critical_project_oidc)
    file_1_1 = FileFactory.create(release=release_1)
    FileEventFactory.create(
        source=file_1_1,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        additional={"publisher_url": "https://fake/url"},
    )

    release_1 = ReleaseFactory.create(project=critical_project_oidc)
    file_1_2 = FileFactory.create(release=release_1)
    FileEventFactory.create(
        source=file_1_2,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
    )

    # Scenario: Same project, differences between releases.
    release_2 = ReleaseFactory.create(project=non_critical_project_oidc)
    file_2 = FileFactory.create(release=release_2)
    FileEventFactory.create(
        source=file_2,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        additional={"publisher_url": "https://fake/url"},
    )

    release_3 = ReleaseFactory.create(project=non_critical_project_oidc)
    file_3 = FileFactory.create(release=release_3)
    FileEventFactory.create(
        source=file_3,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
    )

    compute_oidc_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.total_projects_configured_oidc_publishers", 4),
        pretend.call(
            "warehouse.oidc.total_critical_projects_configured_oidc_publishers", 2
        ),
        pretend.call("warehouse.oidc.total_projects_published_with_oidc_publishers", 2),
        pretend.call(
            "warehouse.oidc.total_critical_projects_published_with_oidc_publishers", 1
        ),
        pretend.call("warehouse.oidc.total_files_published_with_oidc_publishers", 2),
        pretend.call("warehouse.oidc.publishers", 4, tag="github_oidc_publishers"),
    ]
