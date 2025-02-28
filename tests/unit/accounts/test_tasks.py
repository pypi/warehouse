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

from datetime import datetime, timedelta, timezone

import pretend
import pytest

from warehouse.accounts import tasks
from warehouse.accounts.models import TermsOfServiceEngagement
from warehouse.accounts.tasks import compute_user_metrics, notify_users_of_tos_update

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_notify_users_of_tos_update(db_request, user_service, monkeypatch):
    db_request.registry.settings = {"terms.revision": "initial"}
    users_to_notify = UserFactory.create_batch(3, with_verified_primary_email=True)
    # Users we should not notify because they have already agreed to ToS
    UserFactory.create_batch(
        5, with_verified_primary_email=True, with_terms_of_service_agreement=True
    )
    # Users we should not notify because they don't have a primary/verified email
    UserFactory.create_batch(7)

    send_email = pretend.call_recorder(lambda request, user: None)
    monkeypatch.setattr(tasks, "send_user_terms_of_service_updated", send_email)

    user_service.record_tos_engagement = pretend.call_recorder(
        lambda user_id, revision, engagement: None
    )

    notify_users_of_tos_update(db_request)

    assert sorted(send_email.calls, key=lambda x: x.args[1]) == sorted(
        [pretend.call(db_request, u) for u in users_to_notify], key=lambda x: x.args[1]
    )
    assert sorted(
        user_service.record_tos_engagement.calls, key=lambda x: x.args[0]
    ) == sorted(
        [
            pretend.call(u.id, "initial", TermsOfServiceEngagement.Notified)
            for u in users_to_notify
        ],
        key=lambda x: x.args[0],
    )


@pytest.mark.parametrize("batch_size", [0, 10])
def test_notify_users_of_tos_update_respects_batch_size(
    db_request, batch_size, user_service, monkeypatch
):
    db_request.registry.settings = {
        "terms.revision": "initial",
        "terms.notification_batch_size": batch_size,
    }
    UserFactory.create_batch(max(1, batch_size * 2), with_verified_primary_email=True)

    send_email = pretend.call_recorder(lambda request, user: None)
    monkeypatch.setattr(tasks, "send_user_terms_of_service_updated", send_email)

    user_service.record_tos_engagement = pretend.call_recorder(
        lambda user_id, revision, engagement: None
    )

    notify_users_of_tos_update(db_request)

    assert len(send_email.calls) == batch_size
    assert len(user_service.record_tos_engagement.calls) == batch_size


def test_notify_users_of_tos_update_does_not_renotify(
    db_request, user_service, monkeypatch
):
    db_request.registry.settings = {"terms.revision": "initial"}
    users_to_notify = UserFactory.create_batch(3, with_verified_primary_email=True)
    # Users we should not notify because they have already agreed to ToS
    UserFactory.create_batch(
        5, with_verified_primary_email=True, with_terms_of_service_agreement=True
    )
    # Users we should not notify because they don't have a primary/verified email
    UserFactory.create_batch(7)

    send_email = pretend.call_recorder(lambda request, user: None)
    monkeypatch.setattr(tasks, "send_user_terms_of_service_updated", send_email)

    user_service.record_tos_engagement(
        users_to_notify[-1].id, "initial", TermsOfServiceEngagement.Notified
    )

    user_service.record_tos_engagement = pretend.call_recorder(
        lambda user_id, revision, engagement: None
    )

    notify_users_of_tos_update(db_request)

    assert sorted(send_email.calls, key=lambda x: x.args[1]) == sorted(
        [pretend.call(db_request, u) for u in users_to_notify[:-1]],
        key=lambda x: x.args[1],
    )
    assert sorted(
        user_service.record_tos_engagement.calls, key=lambda x: x.args[0]
    ) == sorted(
        [
            pretend.call(u.id, "initial", TermsOfServiceEngagement.Notified)
            for u in users_to_notify[:-1]
        ],
        key=lambda x: x.args[0],
    )


def _create_old_users_and_releases():
    users = UserFactory.create_batch(3, is_active=True)
    for user in users:
        EmailFactory.create(user=user, verified=False)
        project = ProjectFactory.create()
        ReleaseFactory.create(
            project=project,
            uploader=user,
            created=datetime.now(timezone.utc) - timedelta(days=365 * 2 + 1),
        )


def test_compute_user_metrics(db_request, metrics):
    # Create an active user with no email
    UserFactory.create()
    # Create an inactive user
    UserFactory.create(is_active=False)
    # Create a user with an unverified email
    unverified_email_user = UserFactory.create()
    EmailFactory.create(user=unverified_email_user, verified=False)
    # Create a user with a verified email
    verified_email_user = UserFactory.create()
    EmailFactory.create(user=verified_email_user, verified=True)
    # Create a user with a verified email and a release
    verified_email_release_user = UserFactory.create()
    EmailFactory.create(user=verified_email_release_user, verified=True)
    project1 = ProjectFactory.create()
    ReleaseFactory.create(project=project1, uploader=verified_email_release_user)
    # Create an active user with an unverified email and a release
    unverified_email_release_user = UserFactory.create(is_active=True)
    EmailFactory.create(user=unverified_email_release_user, verified=False)
    project2 = ProjectFactory.create()
    ReleaseFactory.create(project=project2, uploader=unverified_email_release_user)
    # Create an active user with an unverified primary email,
    # a verified secondary email, and a release
    unverified_primary_email = UserFactory.create(is_active=True)
    EmailFactory.create(user=unverified_primary_email, verified=False, primary=True)
    EmailFactory.create(user=unverified_primary_email, verified=True, primary=False)
    project3 = ProjectFactory.create()
    ReleaseFactory.create(project=project3, uploader=unverified_primary_email)
    # Create active users with unverified emails and releases over two years
    _create_old_users_and_releases()

    compute_user_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.users.count", 10),
        pretend.call("warehouse.users.count", 9, tags=["active:true"]),
        pretend.call(
            "warehouse.users.count", 7, tags=["active:true", "verified:false"]
        ),
        pretend.call(
            "warehouse.users.count",
            5,
            tags=["active:true", "verified:false", "releases:true"],
        ),
        pretend.call(
            "warehouse.users.count",
            2,
            tags=["active:true", "verified:false", "releases:true", "window:2years"],
        ),
        pretend.call(
            "warehouse.users.count",
            2,
            tags=[
                "active:true",
                "verified:false",
                "releases:true",
                "window:2years",
                "primary:true",
            ],
        ),
    ]
