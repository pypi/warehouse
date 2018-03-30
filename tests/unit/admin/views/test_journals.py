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
import pytest

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.admin.views import journals as views

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    JournalEntryFactory,
    ProjectFactory,
)


class TestProjectList:

    def test_no_query(self, db_request):
        journals = sorted(
            [JournalEntryFactory.create() for _ in range(30)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[:25],
            "query": None,
        }

    def test_with_page(self, db_request):
        journals = sorted(
            [JournalEntryFactory.create() for _ in range(30)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        db_request.GET["page"] = "2"
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[25:],
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.journals_list(request)

    def test_query_basic(self, db_request):
        project0 = ProjectFactory.create()
        project1 = ProjectFactory.create()
        journals0 = sorted(
            [JournalEntryFactory.create(name=project0.normalized_name)
             for _ in range(30)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        [JournalEntryFactory.create(name=project1.normalized_name)
         for _ in range(30)]

        db_request.GET["q"] = '{}'.format(project0.name)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": '{}'.format(project0.name),
        }

    def test_query_term_project(self, db_request):
        project0 = ProjectFactory.create()
        project1 = ProjectFactory.create()
        journals0 = sorted(
            [JournalEntryFactory.create(name=project0.normalized_name)
             for _ in range(30)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        [JournalEntryFactory.create(name=project1.normalized_name)
         for _ in range(30)]

        db_request.GET["q"] = 'project:{}'.format(project0.name)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": 'project:{}'.format(project0.name),
        }

    def test_query_term_user(self, db_request):
        user0 = UserFactory.create()
        user1 = UserFactory.create()
        journals0 = sorted(
            [JournalEntryFactory.create(submitted_by=user0)
             for _ in range(30)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        [JournalEntryFactory.create(submitted_by=user1)
         for _ in range(30)]

        db_request.GET["q"] = 'user:{}'.format(user0.username)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0[:25],
            "query": 'user:{}'.format(user0.username),
        }

    def test_query_term_version(self, db_request):
        journals = (
            [JournalEntryFactory.create()
             for _ in range(10)]
        )

        db_request.GET["q"] = 'version:{}'.format(journals[0].version)
        result = views.journals_list(db_request)

        assert result == {
            "journals": [journals[0]],
            "query": 'version:{}'.format(journals[0].version),
        }

    def test_query_term_ip(self, db_request):
        ipv4 = "10.6.6.6"
        ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        journals0 = sorted(
            [JournalEntryFactory.create(submitted_from=ipv4)
             for _ in range(10)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )
        journals1 = sorted(
            [JournalEntryFactory.create(submitted_from=ipv6)
             for _ in range(10)],
            key=lambda j: (j.submitted_date, j.id),
            reverse=True,
        )

        db_request.GET["q"] = 'ip:{}'.format(ipv4)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals0,
            "query": 'ip:{}'.format(ipv4)
        }

        db_request.GET["q"] = 'ip:{}'.format(ipv6)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals1,
            "query": 'ip:{}'.format(ipv6)
        }
