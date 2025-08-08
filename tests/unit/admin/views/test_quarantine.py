# SPDX-License-Identifier: Apache-2.0

from warehouse.admin.views import quarantine
from warehouse.packaging.models import LifecycleStatus

from ....common.db.packaging import ProjectFactory


class TestQuarantineList:
    def test_quarantine_list_no_projects(self, db_request):
        """Test quarantine list view when no projects are quarantined"""
        result = quarantine.quarantine_list(db_request)
        assert result == {"quarantined_projects": []}

    def test_quarantine_list_with_projects(self, db_request):
        """Test quarantine list view with quarantined projects"""
        # Create some projects in different states
        normal_project = ProjectFactory.create()
        archived_project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.Archived
        )
        quarantined_project_1 = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_note="Test quarantine reason 1",
        )
        quarantined_project_2 = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_note="Test quarantine reason 2",
        )

        result = quarantine.quarantine_list(db_request)

        # Should only return quarantined projects
        assert len(result["quarantined_projects"]) == 2
        project_names = [p.name for p in result["quarantined_projects"]]
        assert quarantined_project_1.name in project_names
        assert quarantined_project_2.name in project_names
        assert normal_project.name not in project_names
        assert archived_project.name not in project_names

    def test_quarantine_list_ordered_by_date(self, db_request):
        """Quarantined projects are ordered by quarantine date (oldest first)"""
        from datetime import datetime, timedelta, timezone

        # Create projects with different quarantine dates
        base_time = datetime.now(timezone.utc)

        newer_project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_changed=base_time,
            lifecycle_status_note="Newer quarantine",
        )
        older_project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_changed=base_time - timedelta(days=5),
            lifecycle_status_note="Older quarantine",
        )

        result = quarantine.quarantine_list(db_request)

        # Should be ordered oldest first
        assert len(result["quarantined_projects"]) == 2
        assert result["quarantined_projects"][0].name == older_project.name
        assert result["quarantined_projects"][1].name == newer_project.name

    def test_quarantine_list_handles_null_date(self, db_request):
        """Projects with null `lifecycle_status_changed` are handled gracefully"""
        # Create a project with no lifecycle_status_changed
        quarantined_project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_changed=None,
            lifecycle_status_note="No date quarantine",
        )

        result = quarantine.quarantine_list(db_request)

        # Should still return the project
        assert len(result["quarantined_projects"]) == 1
        assert result["quarantined_projects"][0].name == quarantined_project.name

    def test_quarantine_list_with_exit_status(self, db_request):
        """Test that projects with quarantine-exit status are not included"""
        # Create projects with different quarantine statuses
        entering_quarantine = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            lifecycle_status_note="Entering quarantine",
        )
        ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineExit,
            lifecycle_status_note="Exiting quarantine",
        )

        result = quarantine.quarantine_list(db_request)

        # Should only return projects entering quarantine
        assert len(result["quarantined_projects"]) == 1
        assert result["quarantined_projects"][0].name == entering_quarantine.name
