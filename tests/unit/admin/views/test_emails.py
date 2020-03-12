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

import csv
import io
import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import emails as views

from ....common.db.accounts import EmailFactory, UserFactory
from ....common.db.ses import EmailMessageFactory


class TestEmailList:
    def test_no_query(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        result = views.email_list(db_request)

        assert result == {"emails": emails[:25], "query": None}

    def test_with_page(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        db_request.GET["page"] = "2"
        result = views.email_list(db_request)

        assert result == {"emails": emails[25:], "query": None}

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

        assert result == {"emails": [emails[0]], "query": emails[0].to}

    def test_wildcard_query(self, db_request):
        emails = sorted(
            [EmailMessageFactory.create() for _ in range(30)],
            key=lambda e: e.created,
            reverse=True,
        )
        db_request.GET["q"] = emails[0].to[:-1] + "%"
        result = views.email_list(db_request)

        assert result == {"emails": [emails[0]], "query": emails[0].to[:-1] + "%"}


class TestEmailMass:
    def test_sends_emails(self, db_request):
        user1 = UserFactory.create()
        email1 = EmailFactory.create(user=user1, primary=True)
        user2 = UserFactory.create()
        email2 = EmailFactory.create(user=user2, primary=True)

        input_file = io.BytesIO()
        wrapper = io.TextIOWrapper(input_file, encoding="utf-8")
        fieldnames = ["user_id", "subject", "body_text"]
        writer = csv.DictWriter(wrapper, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "user_id": user1.id,
                "subject": "Test Subject 1",
                "body_text": "Test Body 1",
            }
        )
        writer.writerow(
            {
                "user_id": user2.id,
                "subject": "Test Subject 2",
                "body_text": "Test Body 2",
            }
        )
        wrapper.seek(0)

        delay = pretend.call_recorder(lambda *a, **kw: None)
        db_request.params = {"csvfile": pretend.stub(file=input_file)}
        db_request.task = lambda a: pretend.stub(delay=delay)
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.email_mass(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert db_request.route_path.calls == [pretend.call("admin.emails.list")]
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Mass emails sent", queue="success")
        ]
        assert delay.calls == [
            pretend.call(
                email1.email,
                {
                    "subject": "Test Subject 1",
                    "body_text": "Test Body 1",
                    "body_html": None,
                },
            ),
            pretend.call(
                email2.email,
                {
                    "subject": "Test Subject 2",
                    "body_text": "Test Body 2",
                    "body_html": None,
                },
            ),
        ]

    def test_user_without_email_sends_no_emails(self, db_request):
        user = UserFactory.create()

        input_file = io.BytesIO()
        wrapper = io.TextIOWrapper(input_file, encoding="utf-8")
        fieldnames = ["user_id", "subject", "body_text"]
        writer = csv.DictWriter(wrapper, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "user_id": user.id,
                "subject": "Test Subject 1",
                "body_text": "Test Body 1",
            }
        )
        wrapper.seek(0)

        delay = pretend.call_recorder(lambda *a, **kw: None)
        db_request.params = {"csvfile": pretend.stub(file=input_file)}
        db_request.task = lambda a: pretend.stub(delay=delay)
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.email_mass(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert db_request.route_path.calls == [pretend.call("admin.emails.list")]
        assert result.headers["Location"] == "/the-redirect"
        assert delay.calls == []

    def test_no_rows_sends_no_emails(self):
        input_file = io.BytesIO()
        wrapper = io.TextIOWrapper(input_file, encoding="utf-8")
        fieldnames = ["user_id", "subject", "body_text"]
        writer = csv.DictWriter(wrapper, fieldnames=fieldnames)
        writer.writeheader()
        wrapper.seek(0)

        delay = pretend.call_recorder(lambda *a, **kw: None)
        request = pretend.stub(
            params={"csvfile": pretend.stub(file=input_file)},
            task=lambda a: pretend.stub(delay=delay),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = views.email_mass(request)

        assert isinstance(result, HTTPSeeOther)
        assert request.route_path.calls == [pretend.call("admin.emails.list")]
        assert result.headers["Location"] == "/the-redirect"
        assert request.session.flash.calls == [
            pretend.call("No emails to send", queue="error")
        ]
        assert delay.calls == []


class TestEmailDetail:
    def test_existing_email(self, db_session):
        em = EmailMessageFactory.create()

        request = pretend.stub(matchdict={"email_id": em.id}, db=db_session)

        assert views.email_detail(request) == {"email": em}

    def test_nonexistent_email(self, db_session):
        EmailMessageFactory.create()

        request = pretend.stub(matchdict={"email_id": str(uuid.uuid4())}, db=db_session)

        with pytest.raises(HTTPNotFound):
            views.email_detail(request)
