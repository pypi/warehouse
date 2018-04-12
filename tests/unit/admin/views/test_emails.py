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

import uuid

import pytest
import pretend

from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from warehouse.admin.views import emails as views

from ....common.db.ses import EmailMessageFactory


class TestEmailList:

    def test_no_query(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        result = views.email_list(db_request)

        assert result == {
            "emails": emails[:25],
            "query": None,
        }

    def test_with_page(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        db_request.GET["page"] = "2"
        result = views.email_list(db_request)

        assert result == {
            "emails": emails[25:],
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.email_list(request)

    def test_basic_query(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        db_request.GET["q"] = emails[0].to
        result = views.email_list(db_request)

        assert result == {
            "emails": [emails[0]],
            "query": emails[0].to,
        }

    def test_wildcard_query(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        db_request.GET["q"] = emails[0].to[:-1] + "%"
        result = views.email_list(db_request)

        assert result == {
            "emails": [emails[0]],
            "query": emails[0].to[:-1] + "%",
        }


class TestEmailDetail:

    def test_existing_email(self, db_session):
        em = EmailMessageFactory.create()

        request = pretend.stub(
            matchdict={"email_id": em.id},
            db=db_session,
        )

        assert views.email_detail(request) == {"email": em}

    def test_nonexistent_email(self, db_session):
        EmailMessageFactory.create()

        request = pretend.stub(
            matchdict={"email_id": str(uuid.uuid4())},
            db=db_session,
        )

        with pytest.raises(HTTPNotFound):
            views.email_detail(request)
