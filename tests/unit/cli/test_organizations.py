# SPDX-License-Identifier: Apache-2.0

import pretend
import pyramid.scripting
import transaction

from warehouse.cli import organizations


class TestOrganizationsCLI:
    def test_send_survey_emails_dry_run(self, monkeypatch, cli):
        """Test dry run doesn't send emails"""
        # Create test organizations
        org1 = pretend.stub(
            id="org1-id",
            name="TestOrg1",
            orgtype=pretend.stub(value="Community"),
            is_active=True,
            projects=[],  # No projects
            users=[
                pretend.stub(
                    username="user1",
                    email="user1@example.com",
                    primary_email=pretend.stub(
                        email="user1@example.com", verified=True
                    ),
                ),
                pretend.stub(
                    username="user2",
                    email="user2@example.com",
                    primary_email=pretend.stub(
                        email="user2@example.com", verified=True
                    ),
                ),
            ],
        )

        org2 = pretend.stub(
            id="org2-id",
            name="TestOrg2",
            orgtype=pretend.stub(value="Company"),
            is_active=True,
            projects=[pretend.stub()],  # Has projects
            users=[
                pretend.stub(
                    username="user3",
                    email="user3@example.com",
                    primary_email=pretend.stub(
                        email="user3@example.com", verified=True
                    ),
                ),
            ],
        )

        # Mock the database query
        query_result = pretend.stub(
            filter=lambda *args: pretend.stub(
                options=lambda *args: pretend.stub(
                    limit=lambda n: pretend.stub(all=lambda: [org1, org2]),
                    all=lambda: [org1, org2],
                )
            )
        )

        # Mock pyramid.scripting.prepare
        mock_request = pretend.stub(
            db=pretend.stub(query=lambda *args: query_result),
            registry={"celery.app": pretend.stub()},
        )
        mock_env = {
            "request": mock_request,
            "closer": pretend.call_recorder(lambda: None),
        }
        prepare = pretend.call_recorder(lambda registry: mock_env)
        monkeypatch.setattr(pyramid.scripting, "prepare", prepare)

        # No need to mock send_organization_survey_email for dry-run test

        # Create config
        config = pretend.stub(
            registry={
                "celery.app": pretend.stub(),
            }
        )

        # Run the command with dry-run
        result = cli.invoke(
            organizations.send_survey_emails,
            ["--dry-run", "--limit", "2"],
            obj=config,
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Would send no_utilization_community survey to user1" in result.output
        assert "Would send no_utilization_community survey to user2" in result.output
        assert "Would send utilization_company survey to user3" in result.output

    def test_send_survey_emails_actual_send(self, monkeypatch, cli):
        """Test actual email sending"""
        # Create test organization
        org = pretend.stub(
            id="org-id",
            name="TestOrg",
            orgtype=pretend.stub(value="Community"),
            is_active=True,
            projects=[pretend.stub()],  # Has projects
            users=[
                pretend.stub(
                    username="user1",
                    email="user1@example.com",
                    primary_email=pretend.stub(
                        email="user1@example.com", verified=True
                    ),
                ),
            ],
        )

        # Mock the database query
        query_result = pretend.stub(
            filter=lambda *args: pretend.stub(
                options=lambda *args: pretend.stub(
                    limit=lambda n: pretend.stub(all=lambda: [org]),
                    all=lambda: [org],
                )
            )
        )

        # Mock transaction manager
        tm = pretend.stub(
            begin=pretend.call_recorder(lambda: None),
            commit=pretend.call_recorder(lambda: None),
        )

        # Mock pyramid.scripting.prepare
        mock_request = pretend.stub(
            db=pretend.stub(query=lambda *args: query_result),
            registry={"celery.app": pretend.stub()},
        )
        mock_env = {
            "request": mock_request,
            "closer": pretend.call_recorder(lambda: None),
        }
        prepare = pretend.call_recorder(lambda registry: mock_env)
        monkeypatch.setattr(pyramid.scripting, "prepare", prepare)

        # Mock transaction.TransactionManager
        monkeypatch.setattr(transaction, "TransactionManager", lambda explicit: tm)

        # Mock _get_task
        mock_get_task = pretend.call_recorder(lambda app, task_func: pretend.stub())
        monkeypatch.setattr("warehouse.tasks._get_task", mock_get_task)

        # Track email sends
        send_email_calls = []

        def mock_send_email(request, user, **kwargs):
            send_email_calls.append((request, user, kwargs))

        monkeypatch.setattr(
            "warehouse.email.send_organization_survey_email",
            mock_send_email,
        )

        # Create config
        config = pretend.stub(
            registry={
                "celery.app": pretend.stub(),
            }
        )

        # Run the command
        result = cli.invoke(
            organizations.send_survey_emails,
            ["--limit", "1"],
            obj=config,
        )

        assert result.exit_code == 0
        assert "Successfully queued 1 emails" in result.output
        assert "Queued utilization_community survey to user1" in result.output
        assert len(send_email_calls) == 1
        assert tm.begin.calls == [pretend.call()]
        assert tm.commit.calls == [pretend.call()]

    def test_send_survey_emails_categorization(self, monkeypatch, cli):
        """Test correct categorization of organizations"""
        # Create test organizations with all 4 categories
        orgs = [
            # Utilization + Company
            pretend.stub(
                name="CompanyWithProjects",
                orgtype=pretend.stub(value="Company"),
                is_active=True,
                projects=[pretend.stub()],
                users=[
                    pretend.stub(
                        username="user1",
                        email="user1@example.com",
                        primary_email=pretend.stub(
                            email="user1@example.com", verified=True
                        ),
                    )
                ],
            ),
            # Utilization + Community
            pretend.stub(
                name="CommunityWithProjects",
                orgtype=pretend.stub(value="Community"),
                is_active=True,
                projects=[pretend.stub()],
                users=[
                    pretend.stub(
                        username="user2",
                        email="user2@example.com",
                        primary_email=pretend.stub(
                            email="user2@example.com", verified=True
                        ),
                    )
                ],
            ),
            # No Utilization + Company
            pretend.stub(
                name="CompanyNoProjects",
                orgtype=pretend.stub(value="Company"),
                is_active=True,
                projects=[],
                users=[
                    pretend.stub(
                        username="user3",
                        email="user3@example.com",
                        primary_email=pretend.stub(
                            email="user3@example.com", verified=True
                        ),
                    )
                ],
            ),
            # No Utilization + Community
            pretend.stub(
                name="CommunityNoProjects",
                orgtype=pretend.stub(value="Community"),
                is_active=True,
                projects=[],
                users=[
                    pretend.stub(
                        username="user4",
                        email="user4@example.com",
                        primary_email=pretend.stub(
                            email="user4@example.com", verified=True
                        ),
                    )
                ],
            ),
        ]

        # Mock the database query
        query_result = pretend.stub(
            filter=lambda *args: pretend.stub(
                options=lambda *args: pretend.stub(all=lambda: orgs)
            )
        )

        # Mock pyramid.scripting.prepare
        mock_request = pretend.stub(
            db=pretend.stub(query=lambda *args: query_result),
            registry={"celery.app": pretend.stub()},
        )
        mock_env = {
            "request": mock_request,
            "closer": pretend.call_recorder(lambda: None),
        }
        prepare = pretend.call_recorder(lambda registry: mock_env)
        monkeypatch.setattr(pyramid.scripting, "prepare", prepare)

        # No need to mock send_organization_survey_email for dry-run test

        # Create config
        config = pretend.stub(
            registry={
                "celery.app": pretend.stub(),
            }
        )

        # Run the command
        result = cli.invoke(
            organizations.send_survey_emails,
            ["--dry-run"],
            obj=config,
        )

        assert result.exit_code == 0
        assert "Utilization + Company: 1" in result.output
        assert "Utilization + Community: 1" in result.output
        assert "No Utilization + Company: 1" in result.output
        assert "No Utilization + Community: 1" in result.output
        assert "Total organizations processed: 4" in result.output
        assert "Total emails to send: 4" in result.output

    def test_send_survey_emails_error_handling(self, monkeypatch, cli):
        """Test error handling when sending emails fails"""
        # Create test organization
        org = pretend.stub(
            name="TestOrg",
            orgtype=pretend.stub(value="Community"),
            is_active=True,
            projects=[],
            users=[
                pretend.stub(
                    username="user1",
                    email="user1@example.com",
                    primary_email=pretend.stub(
                        email="user1@example.com", verified=True
                    ),
                ),
            ],
        )

        # Mock the database query
        query_result = pretend.stub(
            filter=lambda *args: pretend.stub(
                options=lambda *args: pretend.stub(
                    all=lambda: [org],
                    limit=lambda n: pretend.stub(all=lambda: [org]),
                )
            )
        )

        # Mock transaction manager
        tm = pretend.stub(
            begin=pretend.call_recorder(lambda: None),
            commit=pretend.call_recorder(lambda: None),
        )

        # Mock pyramid.scripting.prepare
        mock_request = pretend.stub(
            db=pretend.stub(query=lambda *args: query_result),
            registry={"celery.app": pretend.stub()},
        )
        mock_env = {
            "request": mock_request,
            "closer": pretend.call_recorder(lambda: None),
        }
        prepare = pretend.call_recorder(lambda registry: mock_env)
        monkeypatch.setattr(pyramid.scripting, "prepare", prepare)

        # Mock transaction.TransactionManager
        monkeypatch.setattr(transaction, "TransactionManager", lambda explicit: tm)

        # Mock _get_task
        mock_get_task = pretend.call_recorder(lambda app, task_func: pretend.stub())
        monkeypatch.setattr("warehouse.tasks._get_task", mock_get_task)

        # Make send_email raise an exception
        def mock_send_email(request, user, **kwargs):
            raise Exception("Email sending failed")

        monkeypatch.setattr(
            "warehouse.email.send_organization_survey_email",
            mock_send_email,
        )

        # Create config
        config = pretend.stub(
            registry={
                "celery.app": pretend.stub(),
            }
        )

        # Run the command
        result = cli.invoke(
            organizations.send_survey_emails,
            [],
            obj=config,
        )

        assert result.exit_code == 0
        assert "ERROR sending to user1: Email sending failed" in result.output
        # Transaction should still be committed
        assert tm.commit.calls == [pretend.call()]
