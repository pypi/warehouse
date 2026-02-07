# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone

import pretend
import pytest

from warehouse.observations.models import ObservationKind
from warehouse.observations.tasks import (
    evaluate_project_for_quarantine,
    react_to_observation_created,
    report_observation_to_helpscout,
)
from warehouse.packaging.models import LifecycleStatus

from ...common.db.accounts import UserFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory


def test_execute_observation_report(app_config):
    _delay = pretend.call_recorder(lambda x: None)
    app_config.task = lambda x: pretend.stub(delay=_delay)
    observation = pretend.stub(id=pretend.stub())
    session = pretend.stub(info={"warehouse.observations.new": {observation}})

    react_to_observation_created(app_config, session)

    assert _delay.calls == [pretend.call(observation.id), pretend.call(observation.id)]


@pytest.mark.parametrize(
    ("kind", "reports"),
    [
        (ObservationKind.IsMalware, True),
        (ObservationKind.IsDependencyConfusion, True),
        (ObservationKind.IsSpam, False),
        (ObservationKind.SomethingElse, False),
        (ObservationKind.AccountRecovery, False),
    ],
)
@pytest.mark.parametrize("payload", [{}, {"foo": "bar"}])
def test_report_observation_to_helpscout(
    kind, reports, payload, db_request, helpdesk_service, monkeypatch
):
    db_request.registry.settings = {"helpscout.app_secret": "fake-sekret"}
    db_request.route_url = lambda *a, **kw: "/admin/malware_reports/"

    # Create an Observation
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()
    project_owner = UserFactory.create()
    RoleFactory.create(project=project, user=project_owner, role_name="Owner")

    observation = project.record_observation(
        request=db_request,
        kind=kind,
        summary="Project Observation",
        payload=payload,
        actor=user,
    )
    # Need to flush the session to ensure the Observation has an ID
    db_request.db.flush()

    hs_svc_spy = pretend.call_recorder(lambda *args, **kwargs: None)
    monkeypatch.setattr(helpdesk_service, "create_conversation", hs_svc_spy)

    report_observation_to_helpscout(None, db_request, observation.id)

    # If it's not supposed to report, then we shouldn't have called the service
    assert bool(hs_svc_spy.calls) == reports


class TestAutoQuarantineProject:
    def test_non_malware_observation_does_not_quarantine(self, db_request):
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create()
        db_request.user = user
        project = ProjectFactory.create()

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsDependencyConfusion,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        # Need to flush the session to ensure the Observation has an ID
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call("ObservationKind is not IsMalware. Not quarantining.")
        ]

    def test_already_quarantined_project_does_not_do_anything(self, db_request):
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create()
        db_request.user = user
        project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter
        )

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        # Need to flush the session to ensure the Observation has an ID
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call("Project is already quarantined. No change needed.")
        ]

    def test_not_enough_observers_does_not_quarantine(self, db_request):
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create()
        db_request.user = user
        project = ProjectFactory.create()

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        # Need to flush the session to ensure the Observation has an ID
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call("Project has fewer than 2 observers. Not quarantining.")
        ]

    def test_no_observer_observers_does_not_quarantine(self, db_request):
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create()
        db_request.user = user
        project = ProjectFactory.create()

        another_user = UserFactory.create()

        # Record 2 observations, but neither are from an observer
        project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=another_user,
        )
        # Need to flush the session to ensure the Observations has an ID
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call(
                "Project has no `User.is_observer` Observers. Not quarantining."
            )
        ]

    def test_quarantines_project(self, db_request, notification_service, monkeypatch):
        """
        Satisfies criteria for auto-quarantine:
        - 2 observations
        - from different observers
        - one of which is an Observer
        """
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create(is_observer=True)
        project = ProjectFactory.create()
        # Needs a release to be able to quarantine
        ReleaseFactory.create(project=project)

        another_user = UserFactory.create()

        db_request.route_url = pretend.call_recorder(
            lambda *args, **kw: "/project/spam/"
        )
        db_request.user = user

        # Record 2 observations, one from an observer
        project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=another_user,
        )
        # Need to flush the session to ensure the Observation has an ID
        db_request.db.flush()

        ns_svc_spy = pretend.call_recorder(lambda *args, **kwargs: None)
        monkeypatch.setattr(notification_service, "send_notification", ns_svc_spy)

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert len(ns_svc_spy.calls) == 1
        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call(
                "Auto-quarantining project due to multiple malware observations."
            ),
        ]

    def test_trusted_observer_quarantines_young_project(
        self, db_request, notification_service, monkeypatch
    ):
        """
        A single trusted observer can quarantine a project that is < 24 hours old.
        """
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create(is_observer=True)
        # Create project that was created 1 hour ago
        project = ProjectFactory.create(
            created=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        ReleaseFactory.create(project=project)

        db_request.route_url = pretend.call_recorder(
            lambda *args, **kw: "/project/spam/"
        )
        db_request.user = user

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        db_request.db.flush()

        ns_svc_spy = pretend.call_recorder(lambda *args, **kwargs: None)
        monkeypatch.setattr(notification_service, "send_notification", ns_svc_spy)

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert len(ns_svc_spy.calls) == 1
        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call(
                "Auto-quarantining young project (<24h) reported by trusted observer."
            ),
        ]

    def test_trusted_observer_old_project_needs_corroboration(self, db_request):
        """
        A trusted observer reporting a project > 24 hours old still needs corroboration.
        """
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create(is_observer=True)
        # Create project that was created 25 hours ago
        project = ProjectFactory.create(
            created=datetime.now(timezone.utc) - timedelta(hours=25)
        )
        db_request.user = user

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call("Project has fewer than 2 observers. Not quarantining.")
        ]

    def test_non_trusted_observer_young_project_needs_corroboration(self, db_request):
        """
        A non-trusted observer reporting a young project still needs corroboration.
        """
        dummy_task = pretend.stub(name="dummy_task")
        user = UserFactory.create(is_observer=False)
        # Create project that was created 1 hour ago
        project = ProjectFactory.create(
            created=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        db_request.user = user

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=user,
        )
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert db_request.log.info.calls == [
            pretend.call("Project has fewer than 2 observers. Not quarantining.")
        ]
