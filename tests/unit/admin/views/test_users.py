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

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from sqlalchemy.orm import joinedload
from webob.multidict import MultiDict, NoVars

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import DisableReason
from warehouse.admin.views import users as views
from warehouse.packaging.models import JournalEntry, Project

from ....common.db.accounts import EmailFactory, User, UserFactory
from ....common.db.packaging import JournalEntryFactory, ProjectFactory, RoleFactory


class TestUserList:
    def test_no_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(30)], key=lambda u: u.username.lower()
        )
        result = views.user_list(db_request)

        assert result == {"users": users[:25], "query": None}

    def test_with_page(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(30)], key=lambda u: u.username.lower()
        )
        db_request.GET["page"] = "2"
        result = views.user_list(db_request)

        assert result == {"users": users[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.user_list(request)

    def test_basic_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)], key=lambda u: u.username.lower()
        )
        db_request.GET["q"] = users[0].username
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": users[0].username}

    def test_wildcard_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)], key=lambda u: u.username.lower()
        )
        db_request.GET["q"] = users[0].username[:-1] + "%"
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": users[0].username[:-1] + "%"}

    def test_email_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)], key=lambda u: u.username.lower()
        )
        emails = [EmailFactory.create(user=u, primary=True) for u in users]
        db_request.GET["q"] = "email:" + emails[0].email
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": "email:" + emails[0].email}

    def test_or_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)], key=lambda u: u.username.lower()
        )
        emails = [EmailFactory.create(user=u, primary=True) for u in users]
        db_request.GET["q"] = " ".join(
            [
                users[0].username,
                users[1].username[:-1] + "%",
                "email:" + emails[2].email,
                "email:" + emails[3].email[:-5] + "%",
            ]
        )
        result = views.user_list(db_request)

        assert result == {"users": users[:4], "query": db_request.GET["q"]}

    def test_ignores_invalid_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)], key=lambda u: u.username.lower()
        )
        db_request.GET["q"] = "foobar:what"
        result = views.user_list(db_request)

        assert result == {"users": users, "query": "foobar:what"}


class TestUserDetail:
    def test_404s_on_nonexistent_user(self, db_request):
        user = UserFactory.create()
        user_id = uuid.uuid4()
        while user.id == user_id:
            user_id = uuid.uuid4()
        db_request.matchdict["user_id"] = str(user_id)

        with pytest.raises(HTTPNotFound):
            views.user_detail(db_request)

    def test_gets_user(self, db_request):
        email = EmailFactory.create(primary=True)
        user = UserFactory.create(emails=[email])
        project = ProjectFactory.create()
        roles = sorted([RoleFactory(project=project, user=user, role_name="Owner")])
        db_request.matchdict["user_id"] = str(user.id)
        db_request.POST = NoVars()
        result = views.user_detail(db_request)

        assert result["user"] == user
        assert result["roles"] == roles
        assert result["form"].emails[0].primary.data

    def test_updates_user(self, db_request):
        user = UserFactory.create()
        db_request.matchdict["user_id"] = str(user.id)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST = MultiDict(db_request.POST)
        db_request.current_route_path = pretend.call_recorder(
            lambda: "/admin/users/{}/".format(user.id)
        )

        resp = views.user_detail(db_request)

        assert resp.status_code == 303
        assert resp.location == "/admin/users/{}/".format(user.id)
        assert user.name == "Jane Doe"


class TestUserAddEmail:
    def test_add_email(self, db_request):
        user = UserFactory.create(emails=[])
        db_request.matchdict["user_id"] = str(user.id)
        db_request.method = "POST"
        db_request.POST["email"] = "foo@bar.com"
        db_request.POST["primary"] = True
        db_request.POST["verified"] = True
        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/users/{}/".format(user.id)
        )

        resp = views.user_add_email(db_request)

        db_request.db.flush()

        assert resp.status_code == 303
        assert resp.location == "/admin/users/{}/".format(user.id)
        assert len(user.emails) == 1

        email = user.emails[0]

        assert email.email == "foo@bar.com"
        assert email.primary
        assert email.verified

    def test_add_invalid(self, db_request):
        user = UserFactory.create(emails=[])
        db_request.matchdict["user_id"] = str(user.id)
        db_request.method = "POST"
        db_request.POST["email"] = ""
        db_request.POST["primary"] = True
        db_request.POST["verified"] = True
        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/users/{}/".format(user.id)
        )

        resp = views.user_add_email(db_request)

        db_request.db.flush()

        assert resp.status_code == 303
        assert resp.location == "/admin/users/{}/".format(user.id)
        assert user.emails == []


class TestUserDelete:
    def test_deletes_user(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        another_project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name="Owner")
        deleted_user = UserFactory.create(username="deleted-user")

        # Create an extra JournalEntry by this user which should be
        # updated with the deleted-user user.
        JournalEntryFactory(submitted_by=user, action="some old journal")

        db_request.matchdict["user_id"] = str(user.id)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda a: "/foobar")
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"

        result = views.user_delete(db_request)

        db_request.db.flush()

        assert not db_request.db.query(User).get(user.id)
        assert db_request.db.query(Project).all() == [another_project]
        assert db_request.route_path.calls == [pretend.call("admin.user.list")]
        assert result.status_code == 303
        assert result.location == "/foobar"

        # Check that the correct journals were written/modified
        old_journal = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .filter(JournalEntry.action == "some old journal")
            .one()
        )
        assert old_journal.submitted_by == deleted_user
        remove_journal = (
            db_request.db.query(JournalEntry)
            .filter(JournalEntry.action == "remove project")
            .one()
        )
        assert remove_journal.name == project.name
        nuke_journal = (
            db_request.db.query(JournalEntry)
            .filter(JournalEntry.action == "nuke user")
            .one()
        )
        assert nuke_journal.name == f"user:{user.username}"

    def test_deletes_user_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name="Owner")

        db_request.matchdict["user_id"] = str(user.id)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda a, **k: "/foobar")

        result = views.user_delete(db_request)

        db_request.db.flush()

        assert db_request.db.query(User).get(user.id)
        assert db_request.db.query(Project).all() == [project]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", user_id=user.id)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"


class TestUserResetPassword:
    def test_resets_password(self, db_request, monkeypatch):
        user = UserFactory.create()

        db_request.matchdict["user_id"] = str(user.id)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.id),
            disable_password=pretend.call_recorder(lambda userid, reason: None),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_reset_password(db_request)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, reason=DisableReason.CompromisedPassword)
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", user_id=user.id)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_resets_password_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()

        db_request.matchdict["user_id"] = str(user.id)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.id),
            disable_password=pretend.call_recorder(lambda userid, reason: None),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_reset_password(db_request)

        assert db_request.find_service.calls == []
        assert send_email.calls == []
        assert service.disable_password.calls == []
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", user_id=user.id)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"
