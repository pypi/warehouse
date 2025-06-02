# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.admin.views import journals as views

from ....common.db.accounts import UserFactory
from ....common.db.packaging import JournalEntryFactory, ProjectFactory


class TestProjectList:
    def test_no_query(self, db_request):
        journals = sorted(
            JournalEntryFactory.create_batch(30),
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        result = views.journals_list(db_request)

        assert result == {"journals": journals[:25], "query": None}

    def test_with_page(self, db_request):
        journals = sorted(
            JournalEntryFactory.create_batch(30),
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        db_request.GET["page"] = "2"
        result = views.journals_list(db_request)

        assert result == {"journals": journals[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.journals_list(request)

    def test_query_basic(self, db_request):
        project0 = ProjectFactory.create()
        project1 = ProjectFactory.create()
        journals0 = sorted(
            JournalEntryFactory.create_batch(30, name=project0.normalized_name),
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        JournalEntryFactory.create_batch(30, name=project1.normalized_name)

        db_request.GET["q"] = f"{project0.name}"
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": f"{project0.name}",
        }

    def test_query_term_project(self, db_request):
        project0 = ProjectFactory.create()
        project1 = ProjectFactory.create()
        journals0 = sorted(
            JournalEntryFactory.create_batch(30, name=project0.normalized_name),
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        JournalEntryFactory.create_batch(30, name=project1.normalized_name)

        db_request.GET["q"] = f"project:{project0.name}"
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": f"project:{project0.name}",
        }

    def test_query_term_user(self, db_request):
        user0 = UserFactory.create()
        user1 = UserFactory.create()
        journals0 = sorted(
            JournalEntryFactory.create_batch(30, submitted_by=user0),
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        JournalEntryFactory.create_batch(30, submitted_by=user1)

        db_request.GET["q"] = f"user:{user0.username}"
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": f"user:{user0.username}",
        }

    def test_query_term_version(self, db_request):
        journals = JournalEntryFactory.create_batch(10)

        db_request.GET["q"] = f"version:{journals[0].version}"
        result = views.journals_list(db_request)

        assert result == {
            "journals": [journals[0]],
            "query": f"version:{journals[0].version}",
        }
