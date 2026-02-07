# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from warehouse.macaroons import caveats
from warehouse.macaroons.models import Macaroon
from warehouse.oidc.tasks import compute_oidc_metrics, delete_expired_oidc_macaroons

from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import (
    FileEventFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    UserFactory,
)


def test_compute_oidc_metrics(db_request, metrics):
    # Projects with OIDC
    project_oidc_one = ProjectFactory.create(name="project_oidc_one")
    project_oidc_two = ProjectFactory.create(name="project_oidc_two")
    non_released_project_oidc = ProjectFactory.create(
        name="non_released_project_oidc",
    )

    # Projects without OIDC
    ProjectFactory.create(name="project_no_oidc")

    # Create an OIDC publisher that's shared by multiple projects.
    GitHubPublisherFactory.create(projects=[project_oidc_one])
    GitHubPublisherFactory.create(projects=[project_oidc_two])

    # Create an OIDC publisher that is only used by one project.
    GitHubPublisherFactory.create(projects=[project_oidc_one])

    # Create OIDC publishers for projects which have no releases.
    GitHubPublisherFactory.create(projects=[non_released_project_oidc])

    # Create some files which have/have not been published
    # using OIDC in different scenarios.

    # Scenario: Same release, difference between files.
    release_1 = ReleaseFactory.create(project=project_oidc_one)
    file_1_1 = FileFactory.create(release=release_1)
    FileEventFactory.create(
        source=file_1_1,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        additional={"publisher_url": "https://fake/url"},
    )

    release_1 = ReleaseFactory.create(project=project_oidc_one)
    file_1_2 = FileFactory.create(release=release_1)
    FileEventFactory.create(
        source=file_1_2,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
    )

    # Scenario: Same project, differences between releases.
    release_2 = ReleaseFactory.create(project=project_oidc_two)
    file_2 = FileFactory.create(release=release_2)
    FileEventFactory.create(
        source=file_2,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        additional={"publisher_url": "https://fake/url"},
    )

    release_3 = ReleaseFactory.create(project=project_oidc_two)
    file_3 = FileFactory.create(release=release_3)
    FileEventFactory.create(
        source=file_3,
        tag="fake:event",
        time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
    )

    compute_oidc_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.total_projects_configured_oidc_publishers", 3),
        pretend.call("warehouse.oidc.total_projects_published_with_oidc_publishers", 2),
        pretend.call("warehouse.oidc.total_files_published_with_oidc_publishers", 2),
        pretend.call(
            "warehouse.oidc.publishers", 4, tags=["publisher:github_oidc_publishers"]
        ),
    ]


def test_delete_expired_oidc_macaroons(db_request, macaroon_service, metrics):
    # We'll create 4 macaroons:
    # - An OIDC macaroon with creation time of 1 day ago
    # - An OIDC macaroon with creation time of 1 hour ago
    # - An OIDC macaroon with creation time now
    # - A non-OIDC macaroon with creation time of 1 day ago
    # The task should only delete the first one

    publisher = GitHubPublisherFactory.create()
    claims = {"sha": "somesha", "ref": "someref"}
    # Create an OIDC macaroon and set its creation time to 1 day ago
    _, old_oidc_macaroon = macaroon_service.create_macaroon(
        "fake location",
        "fake description",
        [
            caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id)),
        ],
        oidc_publisher_id=publisher.id,
        additional={"oidc": publisher.stored_claims(claims)},
    )
    old_oidc_macaroon.created -= datetime.timedelta(days=1)

    # Create an OIDC macaroon and set its creation time to 1 hour ago
    macaroon_service.create_macaroon(
        "fake location",
        "fake description",
        [
            caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id)),
        ],
        oidc_publisher_id=publisher.id,
        additional={"oidc": publisher.stored_claims(claims)},
    )
    old_oidc_macaroon.created -= datetime.timedelta(hours=1)

    # Create a normal OIDC macaroon
    macaroon_service.create_macaroon(
        "fake location",
        "fake description",
        [caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id))],
        oidc_publisher_id=publisher.id,
        additional={"oidc": publisher.stored_claims(claims)},
    )

    # Create a non-OIDC macaroon and set its creation time to 1 day ago
    user = UserFactory.create()
    _, non_oidc_macaroon = macaroon_service.create_macaroon(
        "fake location",
        "fake description",
        [caveats.RequestUser(user_id=str(user.id))],
        user_id=user.id,
    )
    non_oidc_macaroon.created -= datetime.timedelta(days=1)

    assert db_request.db.query(Macaroon).count() == 4

    # The ID of the macaroon we expect to be deleted by the task
    old_oidc_macaroon_id = old_oidc_macaroon.id

    delete_expired_oidc_macaroons(db_request)
    assert db_request.db.query(Macaroon).count() == 3
    assert (
        db_request.db.query(Macaroon)
        .filter(Macaroon.id == old_oidc_macaroon_id)
        .count()
        == 0
    )

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.expired_oidc_tokens_deleted", 1),
    ]
