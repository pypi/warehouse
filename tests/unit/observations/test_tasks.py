# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta

import pytest

from structlog.stdlib import BoundLogger

from warehouse.observations.models import ObservationKind
from warehouse.observations.tasks import (
    evaluate_project_for_quarantine,
    react_to_observation_created,
    report_observation_to_helpscout,
)
from warehouse.packaging.models import LifecycleStatus
from warehouse.tasks import WarehouseTask

from ...common.db.accounts import UserFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory


def test_execute_observation_report(app_config, db_request, mocker):
    tasks = {
        report_observation_to_helpscout: mocker.create_autospec(
            WarehouseTask, instance=True
        ),
        evaluate_project_for_quarantine: mocker.create_autospec(
            WarehouseTask, instance=True
        ),
    }
    task = mocker.patch.object(
        app_config, "task", autospec=True, side_effect=tasks.__getitem__
    )
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
    db_request.db.flush()

    react_to_observation_created(app_config, db_request.db)

    assert task.call_args_list == [
        mocker.call(report_observation_to_helpscout),
        mocker.call(evaluate_project_for_quarantine),
    ]
    tasks[report_observation_to_helpscout].delay.assert_called_once_with(observation.id)
    tasks[evaluate_project_for_quarantine].delay.assert_called_once_with(observation.id)
    assert "warehouse.observations.new" not in db_request.db.info


def _record_reportable_observation(db_request, kind, payload):
    """Record an Observation by a fresh user on a project with one Owner."""
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
    return project, project_owner, observation


@pytest.fixture
def warehouse_domain(db_request):
    """Configure the host that route_url links must point at."""
    domain = "pypi.example"
    db_request.registry.settings.update({"warehouse.domain": domain})
    return domain


@pytest.mark.parametrize(
    ("kind", "extra_routes"),
    [
        (ObservationKind.IsMalware, ["admin.malware_reports.project.list"]),
        (ObservationKind.IsDependencyConfusion, []),
    ],
)
@pytest.mark.parametrize(
    ("payload", "expected_attachments"),
    [
        ({}, lambda project, observation: {}),
        (
            {"foo": "bar"},
            lambda project, observation: {
                "attachments": [
                    {
                        "fileName": (
                            f"observation-{project.name}-{observation.created}.json"
                        ),
                        "mimeType": "application/json",
                        "data": "eyJmb28iOiAiYmFyIn0=",
                    }
                ]
            },
        ),
    ],
    ids=["no_payload", "payload"],
)
def test_report_observation_to_helpscout(
    kind,
    extra_routes,
    payload,
    expected_attachments,
    db_request,
    warehouse_domain,
    helpdesk_service,
    mocker,
):
    route_url = mocker.patch.object(
        db_request,
        "route_url",
        autospec=True,
        side_effect=lambda route, **kw: f"https://{kw['_host']}/{route}/",
    )
    project, project_owner, observation = _record_reportable_observation(
        db_request, kind, payload
    )
    observer_email = db_request.user.email
    create_conversation = mocker.spy(helpdesk_service, "create_conversation")

    report_observation_to_helpscout(None, db_request, observation.id)

    create_conversation.assert_called_once_with(request_json=mocker.ANY)
    request_json = create_conversation.call_args.kwargs["request_json"]
    assert request_json["subject"] == f"Observation Report for {project.name}"
    assert request_json["mailboxId"] == helpdesk_service.mailbox_id
    assert request_json["customer"] == {"email": observer_email}
    assert request_json["tags"] == ["observation"]
    assert request_json["threads"] == [
        {
            "type": "customer",
            "customer": {"email": observer_email},
            "text": mocker.ANY,
            **expected_attachments(project, observation),
        }
    ]
    text = request_json["threads"][0]["text"]
    assert f"Owner: {project_owner.username}\n" in text
    for route in ["packaging.project", "admin.user.detail", *extra_routes]:
        assert f"https://{warehouse_domain}/{route}/" in text
    assert route_url.call_args_list == [
        mocker.call("packaging.project", name=project.name, _host=warehouse_domain),
        mocker.call(
            "admin.user.detail",
            username=project_owner.username,
            _host=warehouse_domain,
        ),
        *[
            mocker.call(route, project_name=project.name, _host=warehouse_domain)
            for route in extra_routes
        ],
    ]
    assert observation.additional["helpscout_conversation_url"] == "localhost"


@pytest.mark.parametrize(
    "kind",
    [
        ObservationKind.IsSpam,
        ObservationKind.SomethingElse,
        ObservationKind.AccountRecovery,
    ],
)
def test_report_observation_to_helpscout_skips_unreported_kinds(
    kind, db_request, helpdesk_service, mocker
):
    route_url = mocker.patch.object(db_request, "route_url", autospec=True)
    _, _, observation = _record_reportable_observation(db_request, kind, {})
    create_conversation = mocker.spy(helpdesk_service, "create_conversation")

    report_observation_to_helpscout(None, db_request, observation.id)

    create_conversation.assert_not_called()
    route_url.assert_not_called()
    assert "helpscout_conversation_url" not in observation.additional


def test_report_observation_to_quarantined_project_tags_conversation(
    db_request, warehouse_domain, helpdesk_service, mocker
):
    route_url = mocker.patch.object(
        db_request, "route_url", autospec=True, return_value="/admin/malware_reports/"
    )
    user = UserFactory.create()
    project = ProjectFactory.create(lifecycle_status=LifecycleStatus.QuarantineEnter)
    observation = project.record_observation(
        request=db_request,
        kind=ObservationKind.IsMalware,
        summary="Project Observation",
        payload={},
        actor=user,
    )
    db_request.db.flush()
    create_conversation = mocker.patch.object(
        helpdesk_service,
        "create_conversation",
        autospec=True,
        return_value="https://example.com/c/1",
    )

    report_observation_to_helpscout(None, db_request, observation.id)

    request_json = create_conversation.call_args.kwargs["request_json"]
    assert request_json["tags"] == ["observation", "quarantined_via_auto"]
    assert route_url.call_args_list == [
        mocker.call("packaging.project", name=project.name, _host=warehouse_domain),
        mocker.call(
            "admin.malware_reports.project.list",
            project_name=project.name,
            _host=warehouse_domain,
        ),
    ]


def assert_quarantine_notification(
    mocker, send_notification, route_url, project, warehouse_domain
):
    """Assert the admin notification links to the quarantined project."""
    send_notification.assert_called_once_with(payload=mocker.ANY)
    payload = send_notification.call_args.kwargs["payload"]
    assert payload["blocks"][0]["text"]["text"] == (
        f"*Auto-Quarantine: <{route_url.return_value}|{project.name}>*"
    )
    assert route_url.call_args_list == [
        mocker.call(
            "packaging.project", name=project.normalized_name, _host=warehouse_domain
        ),
        mocker.call(
            "admin.malware_reports.project.list",
            project_name=project.normalized_name,
            _host=warehouse_domain,
        ),
    ]


def assert_logger_bound(
    db_request, task, observer, project, kind=ObservationKind.IsMalware
):
    """Assert the task bound its logger to the observation's context."""
    db_request.log.bind.assert_called_once_with(
        kind=kind.value[0],
        observer=observer.username,
        project=project.name,
        task=task.name,
    )


class TestAutoQuarantineProject:
    @pytest.fixture
    def dummy_task(self, mocker):
        task = mocker.create_autospec(WarehouseTask, instance=True)
        task.name = "evaluate_project_for_quarantine"
        return task

    @pytest.fixture
    def logger(self, db_request, mocker):
        """Give ``request.log.bind`` a bound logger distinct from ``request.log``."""
        db_request.log = mocker.create_autospec(BoundLogger, instance=True)
        db_request.log.bind.return_value = mocker.create_autospec(
            BoundLogger, instance=True
        )
        return db_request.log.bind.return_value

    def test_non_malware_observation_does_not_quarantine(
        self, dummy_task, logger, db_request, mocker
    ):
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
        assert_logger_bound(
            db_request,
            dummy_task,
            user,
            project,
            kind=ObservationKind.IsDependencyConfusion,
        )
        assert logger.info.call_args_list == [
            mocker.call("ObservationKind is not IsMalware. Not quarantining.")
        ]

    def test_already_quarantined_project_does_not_do_anything(
        self, dummy_task, logger, db_request, mocker
    ):
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
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call("Project is already quarantined. No change needed.")
        ]

    def test_not_enough_observers_does_not_quarantine(
        self, dummy_task, logger, db_request, mocker
    ):
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
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call("Project has fewer than 2 observers. Not quarantining.")
        ]

    def test_non_malware_observations_do_not_corroborate(
        self, dummy_task, logger, db_request, mocker
    ):
        """Only malware reports count toward the corroboration threshold."""
        observer_user = UserFactory.create(is_observer=True)
        another_user = UserFactory.create()
        db_request.user = observer_user
        # An older project, so the trusted-observer fast-track doesn't apply
        project = ProjectFactory.create(created=datetime.now(UTC) - timedelta(days=30))

        observation = project.record_observation(
            request=db_request,
            kind=ObservationKind.IsMalware,
            summary="Project Observation",
            payload={},
            actor=observer_user,
        )
        project.record_observation(
            request=db_request,
            kind=ObservationKind.IsSpam,
            summary="Project Observation",
            payload={},
            actor=another_user,
        )
        db_request.db.flush()

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert project.lifecycle_status != LifecycleStatus.QuarantineEnter
        assert_logger_bound(db_request, dummy_task, observer_user, project)
        assert logger.info.call_args_list == [
            mocker.call("Project has fewer than 2 observers. Not quarantining.")
        ]

    def test_no_observer_observers_does_not_quarantine(
        self, dummy_task, logger, db_request, mocker
    ):
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
        assert_logger_bound(db_request, dummy_task, another_user, project)
        assert logger.info.call_args_list == [
            mocker.call(
                "Project has no `User.is_observer` Observers. Not quarantining."
            )
        ]

    def test_quarantines_project(
        self,
        dummy_task,
        logger,
        db_request,
        notification_service,
        warehouse_domain,
        mocker,
    ):
        """
        Satisfies criteria for auto-quarantine:
        - 2 observations
        - from different observers
        - one of which is an Observer
        """
        user = UserFactory.create(is_observer=True)
        project = ProjectFactory.create()
        # Needs a release to be able to quarantine
        ReleaseFactory.create(project=project)

        another_user = UserFactory.create()

        route_url = mocker.patch.object(
            db_request, "route_url", autospec=True, return_value="/project/spam/"
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

        send_notification = mocker.spy(notification_service, "send_notification")

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert_quarantine_notification(
            mocker, send_notification, route_url, project, warehouse_domain
        )
        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert_logger_bound(db_request, dummy_task, another_user, project)
        assert logger.info.call_args_list == [
            mocker.call(
                "Auto-quarantining project due to multiple malware observations."
            ),
        ]

    def test_trusted_observer_quarantines_young_project(
        self,
        dummy_task,
        logger,
        db_request,
        notification_service,
        warehouse_domain,
        mocker,
    ):
        """
        A single trusted observer can quarantine a project that is < 24 hours old.
        """
        user = UserFactory.create(is_observer=True)
        # Create project that was created 1 hour ago
        project = ProjectFactory.create(created=datetime.now(UTC) - timedelta(hours=1))
        ReleaseFactory.create(project=project)

        route_url = mocker.patch.object(
            db_request, "route_url", autospec=True, return_value="/project/spam/"
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

        send_notification = mocker.spy(notification_service, "send_notification")

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert_quarantine_notification(
            mocker, send_notification, route_url, project, warehouse_domain
        )
        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call(
                "Auto-quarantining young project (<24h) reported by trusted observer."
            ),
        ]

    def test_trusted_observer_quarantines_young_project_with_yanked_releases(
        self,
        dummy_task,
        logger,
        db_request,
        notification_service,
        warehouse_domain,
        mocker,
    ):
        """
        A young project where all releases are yanked should still be quarantined.
        latest_version is None when all releases are yanked.
        """
        user = UserFactory.create(is_observer=True)
        project = ProjectFactory.create(created=datetime.now(UTC) - timedelta(hours=1))
        ReleaseFactory.create(project=project, yanked=True)

        route_url = mocker.patch.object(
            db_request, "route_url", autospec=True, return_value="/project/spam/"
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

        send_notification = mocker.spy(notification_service, "send_notification")

        evaluate_project_for_quarantine(dummy_task, db_request, observation.id)

        assert_quarantine_notification(
            mocker, send_notification, route_url, project, warehouse_domain
        )
        assert project.lifecycle_status == LifecycleStatus.QuarantineEnter
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call(
                "Auto-quarantining young project (<24h) reported by trusted observer."
            ),
        ]

    def test_trusted_observer_old_project_needs_corroboration(
        self, dummy_task, logger, db_request, mocker
    ):
        """
        A trusted observer reporting a project > 24 hours old still needs corroboration.
        """
        user = UserFactory.create(is_observer=True)
        # Create project that was created 25 hours ago
        project = ProjectFactory.create(created=datetime.now(UTC) - timedelta(hours=25))
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
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call("Project has fewer than 2 observers. Not quarantining.")
        ]

    def test_non_trusted_observer_young_project_needs_corroboration(
        self, dummy_task, logger, db_request, mocker
    ):
        """
        A non-trusted observer reporting a young project still needs corroboration.
        """
        user = UserFactory.create(is_observer=False)
        # Create project that was created 1 hour ago
        project = ProjectFactory.create(created=datetime.now(UTC) - timedelta(hours=1))
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
        assert_logger_bound(db_request, dummy_task, user, project)
        assert logger.info.call_args_list == [
            mocker.call("Project has fewer than 2 observers. Not quarantining.")
        ]
