# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.models import Macaroon
from warehouse.oidc.models import PendingOIDCPublisher
from warehouse.oidc.tasks import (
    PENDING_PUBLISHER_EXPIRY_DAYS,
    PENDING_PUBLISHER_REMINDER_DAYS,
    compute_oidc_metrics,
    delete_expired_oidc_macaroons,
    delete_expired_pending_publishers,
    pending_publisher_cutoff,
    send_pending_publisher_expiration_reminders,
)

from ...common.db.oidc import GitHubPublisherFactory, PendingGitHubPublisherFactory
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

    # Create some pending publishers (not yet associated with a real project).
    PendingGitHubPublisherFactory.create_batch(2)

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
        pretend.call(
            "warehouse.oidc.pending_publishers",
            2,
            tags=["publisher:pending_github_oidc_publishers"],
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


def test_delete_expired_pending_publishers(db_request, metrics, monkeypatch):
    """Expired pending publishers are deleted and their owners notified."""
    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(
        "warehouse.oidc.tasks.send_pending_trusted_publisher_expired_email",
        send_email,
    )

    expired_publisher = PendingGitHubPublisherFactory.create(
        project_name="expired-project",
        created=pending_publisher_cutoff(PENDING_PUBLISHER_EXPIRY_DAYS)
        - datetime.timedelta(seconds=1),
    )
    fresh_publisher = PendingGitHubPublisherFactory.create(
        project_name="fresh-project",
    )
    record_event = pretend.call_recorder(lambda **kw: None)
    expired_publisher.added_by.record_event = record_event

    assert db_request.db.query(PendingOIDCPublisher).count() == 2

    delete_expired_pending_publishers(db_request)

    # Only the fresh publisher should remain
    assert db_request.db.query(PendingOIDCPublisher).count() == 1
    remaining = db_request.db.query(PendingOIDCPublisher).one()
    assert remaining.project_name == fresh_publisher.project_name

    # Email was sent to the expired publisher's owner
    assert send_email.calls == [
        pretend.call(
            db_request,
            expired_publisher.added_by,
            project_name="expired-project",
            days=PENDING_PUBLISHER_EXPIRY_DAYS,
        ),
    ]

    # An auto-removal event was recorded against the registrant, with
    # location redacted (system action, not user-initiated).
    assert record_event.calls == [
        pretend.call(
            tag=EventTag.Account.PendingOIDCPublisherRemoved,
            request=db_request,
            additional={
                "project": "expired-project",
                "publisher": expired_publisher.publisher_name,
                "id": str(expired_publisher.id),
                "specifier": str(expired_publisher),
                "url": expired_publisher.publisher_url(),
                "submitted_by": "system:ttl-expired",
                "redact_ip": True,
            },
        )
    ]

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.expired_pending_publishers_deleted", 1),
    ]


def test_delete_expired_pending_publishers_none_expired(
    db_request, metrics, monkeypatch
):
    """When no pending publishers are expired, nothing is deleted."""
    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(
        "warehouse.oidc.tasks.send_pending_trusted_publisher_expired_email",
        send_email,
    )

    PendingGitHubPublisherFactory.create(project_name="fresh-project")

    delete_expired_pending_publishers(db_request)

    assert db_request.db.query(PendingOIDCPublisher).count() == 1
    assert send_email.calls == []
    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.expired_pending_publishers_deleted", 0),
    ]


def test_send_pending_publisher_expiration_reminders(db_request, metrics, monkeypatch):
    """Pending publishers in the reminder window get a one-shot reminder email."""
    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(
        "warehouse.oidc.tasks.send_pending_trusted_publisher_expiration_reminder_email",
        send_email,
    )

    reminder_cutoff = pending_publisher_cutoff(
        PENDING_PUBLISHER_EXPIRY_DAYS - PENDING_PUBLISHER_REMINDER_DAYS
    )
    needs_reminder = PendingGitHubPublisherFactory.create(
        project_name="needs-reminder",
        created=reminder_cutoff - datetime.timedelta(seconds=1),
    )
    already_reminded = PendingGitHubPublisherFactory.create(
        project_name="already-reminded",
        created=reminder_cutoff - datetime.timedelta(seconds=1),
        expiration_reminded=True,
    )
    fresh = PendingGitHubPublisherFactory.create(project_name="fresh-project")

    send_pending_publisher_expiration_reminders(db_request)

    assert send_email.calls == [
        pretend.call(
            db_request,
            needs_reminder.added_by,
            project_name="needs-reminder",
            days_remaining=PENDING_PUBLISHER_REMINDER_DAYS,
        ),
    ]

    assert needs_reminder.expiration_reminded is True
    assert already_reminded.expiration_reminded is True
    assert fresh.expiration_reminded is False

    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.pending_publisher_expiration_reminders_sent", 1),
    ]


def test_send_pending_publisher_expiration_reminders_none_due(
    db_request, metrics, monkeypatch
):
    """When no pending publishers are in the reminder window, nothing is sent."""
    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(
        "warehouse.oidc.tasks.send_pending_trusted_publisher_expiration_reminder_email",
        send_email,
    )

    PendingGitHubPublisherFactory.create(project_name="fresh-project")

    send_pending_publisher_expiration_reminders(db_request)

    assert send_email.calls == []
    assert metrics.gauge.calls == [
        pretend.call("warehouse.oidc.pending_publisher_expiration_reminders_sent", 0),
    ]
