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

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently
from sqlalchemy.orm import joinedload
from webob.multidict import MultiDict, NoVars

from warehouse.accounts.interfaces import IEmailBreachedService, IUserService
from warehouse.accounts.models import (
    DisableReason,
    ProhibitedEmailDomain,
    ProhibitedUserName,
    RecoveryCode,
    WebAuthn,
)
from warehouse.admin.views import users as views
from warehouse.packaging.models import JournalEntry, Project

from ....common.db.accounts import EmailFactory, User, UserFactory
from ....common.db.packaging import JournalEntryFactory, ProjectFactory, RoleFactory


class TestUserList:
    def test_no_query(self, db_request):
        users = sorted(UserFactory.create_batch(30), key=lambda u: u.username.lower())
        result = views.user_list(db_request)

        assert result == {"users": users[:25], "query": None}

    def test_with_page(self, db_request):
        users = sorted(UserFactory.create_batch(30), key=lambda u: u.username.lower())
        db_request.GET["page"] = "2"
        result = views.user_list(db_request)

        assert result == {"users": users[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.user_list(request)

    def test_basic_query(self, db_request):
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
        db_request.GET["q"] = users[0].username
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": users[0].username}

    def test_wildcard_query(self, db_request):
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
        db_request.GET["q"] = users[0].username[:-1] + "%"
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": users[0].username[:-1] + "%"}

    def test_email_query(self, db_request):
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
        emails = [EmailFactory.create(user=u, primary=True) for u in users]
        db_request.GET["q"] = "email:" + emails[0].email
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": "email:" + emails[0].email}

    def test_id_query(self, db_request):
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
        db_request.GET["q"] = "id:" + str(users[0].id)
        result = views.user_list(db_request)

        assert result == {"users": [users[0]], "query": "id:" + str(users[0].id)}

    def test_or_query(self, db_request):
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
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
        users = sorted(UserFactory.create_batch(5), key=lambda u: u.username.lower())
        db_request.GET["q"] = "foobar:what"
        result = views.user_list(db_request)

        assert result == {"users": users, "query": "foobar:what"}


class TestEmailForm:
    def test_validate(self):
        form = views.EmailForm(formdata=MultiDict({"email": "foo@bar.net"}))
        assert form.validate(), str(form.errors)


class TestUserForm:
    def test_validate(self):
        form = views.UserForm()
        assert form.validate(), str(form.erros)


class TestUserDetail:
    def test_gets_user(self, db_request):
        email = EmailFactory.create(primary=True)
        user = UserFactory.create(emails=[email])
        project = ProjectFactory.create()
        roles = sorted([RoleFactory(project=project, user=user, role_name="Owner")])
        db_request.matchdict["username"] = str(user.username)
        db_request.POST = NoVars()

        breach_service = pretend.stub(get_email_breach_count=lambda count: 0)
        db_request.find_service = lambda interface, **kwargs: {
            IEmailBreachedService: breach_service,
        }[interface]

        result = views.user_detail(user, db_request)

        assert result["user"] == user
        assert result["roles"] == roles
        assert result["form"].emails[0].primary.data

    def test_updates_user(self, db_request):
        user = UserFactory.create()
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST = MultiDict(db_request.POST)
        db_request.current_route_path = pretend.call_recorder(
            lambda: f"/admin/users/{user.username}/"
        )

        resp = views.user_detail(user, db_request)

        assert resp.status_code == 303
        assert resp.location == f"/admin/users/{user.username}/"
        assert user.name == "Jane Doe"

    def test_updates_user_no_primary_email(self, db_request):
        email = EmailFactory.create(primary=True)
        user = UserFactory.create(emails=[email])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST["emails-0-email"] = email.email
        # No primary = checkbox unchecked

        db_request.POST = MultiDict(db_request.POST)
        db_request.current_route_path = pretend.call_recorder(
            lambda: f"/admin/users/{user.username}/"
        )

        breach_service = pretend.stub(get_email_breach_count=lambda count: 0)
        db_request.find_service = lambda interface, **kwargs: {
            IEmailBreachedService: breach_service,
        }[interface]

        resp = views.user_detail(user, db_request)

        assert resp["form"].errors == {
            "emails": ["There must be exactly one primary email"]
        }

    def test_updates_user_multiple_primary_emails(self, db_request):
        email1 = EmailFactory.create(primary=True)
        email2 = EmailFactory.create(primary=True)
        user = UserFactory.create(emails=[email1, email2])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST["emails-0-email"] = email1.email
        db_request.POST["emails-0-primary"] = "true"
        db_request.POST["emails-1-email"] = email2.email
        db_request.POST["emails-1-primary"] = "true"
        # No primary = checkbox unchecked

        db_request.POST = MultiDict(db_request.POST)
        db_request.current_route_path = pretend.call_recorder(
            lambda: f"/admin/users/{user.username}/"
        )

        breach_service = pretend.stub(get_email_breach_count=lambda count: 0)
        db_request.find_service = lambda interface, **kwargs: {
            IEmailBreachedService: breach_service,
        }[interface]

        resp = views.user_detail(user, db_request)

        assert resp["form"].errors == {
            "emails": ["There must be exactly one primary email"]
        }

    def test_user_detail_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_detail(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestUserAddEmail:
    def test_add_primary_email(self, db_request):
        old_email = EmailFactory.create(email="old@bar.com", primary=True)
        user = UserFactory.create(emails=[old_email])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["email"] = "foo@bar.com"
        db_request.POST["primary"] = True
        db_request.POST["verified"] = True
        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/users/{user.username}/"
        )

        resp = views.user_add_email(user, db_request)

        db_request.db.flush()

        assert resp.status_code == 303
        assert resp.location == f"/admin/users/{user.username}/"
        assert len(user.emails) == 2

        emails = {e.email: e for e in user.emails}

        assert not emails["old@bar.com"].primary
        assert emails["foo@bar.com"].primary
        assert emails["foo@bar.com"].verified

    def test_add_non_primary_email(self, db_request):
        old_email = EmailFactory.create(email="old@bar.com", primary=True)
        user = UserFactory.create(emails=[old_email])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["email"] = "foo@bar.com"
        # No "primary" field
        db_request.POST["verified"] = True
        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/users/{user.username}/"
        )

        resp = views.user_add_email(user, db_request)

        db_request.db.flush()

        assert resp.status_code == 303
        assert resp.location == f"/admin/users/{user.username}/"
        assert len(user.emails) == 2

        emails = {e.email: e for e in user.emails}

        assert emails["old@bar.com"].primary
        assert not emails["foo@bar.com"].primary

    def test_add_invalid(self, db_request):
        user = UserFactory.create(emails=[])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["email"] = ""
        db_request.POST["primary"] = True
        db_request.POST["verified"] = True
        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/admin/users/{user.username}/"
        )

        resp = views.user_add_email(user, db_request)

        db_request.db.flush()

        assert resp.status_code == 303
        assert resp.location == f"/admin/users/{user.username}/"
        assert user.emails == []

    def test_user_add_email_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_add_email(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestUserDelete:
    def test_deletes_user(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        another_project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name="Owner")
        deleted_user = UserFactory.create(username="deleted-user")

        # Create an extra JournalEntry by this user which should be
        # updated with the deleted-user user.
        JournalEntryFactory.create(submitted_by=user, action="some old journal")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda a: "/foobar")
        db_request.user = UserFactory.create()

        result = views.user_delete(user, db_request)

        db_request.db.flush()

        assert not db_request.db.get(User, user.id)
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

    def test_deletes_user_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name="Owner")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda a, **k: "/foobar")

        result = views.user_delete(user, db_request)

        db_request.db.flush()

        assert db_request.db.get(User, user.id)
        assert db_request.db.query(Project).all() == [project]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_delete_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_delete(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestUserFreeze:
    def test_freezes_user(self, db_request, monkeypatch):
        user = UserFactory.create()
        verified_email = EmailFactory.create(user=user, verified=True, primary=True)
        EmailFactory.create(user=user, verified=False, primary=False)

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda a: "/foobar")
        db_request.user = UserFactory.create()

        result = views.user_freeze(user, db_request)

        db_request.db.flush()

        assert db_request.db.get(User, user.id).is_frozen
        prohibition = db_request.db.query(ProhibitedEmailDomain).one()
        assert prohibition.domain == verified_email.domain

        assert db_request.route_path.calls == [pretend.call("admin.user.list")]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_freezes_user_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create(is_frozen=False)
        EmailFactory.create(user=user, verified=True, primary=True)

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda a, **k: "/foobar")

        result = views.user_freeze(user, db_request)

        db_request.db.flush()

        assert not db_request.db.get(User, user.id).is_frozen
        assert not db_request.db.query(ProhibitedEmailDomain).all()
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_freeze_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_freeze(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestUserResetPassword:
    def test_resets_password(self, db_request, monkeypatch):
        user = UserFactory.create()

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = UserFactory.create()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.username),
            disable_password=pretend.call_recorder(
                lambda userid, request, reason: None
            ),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_reset_password(user, db_request)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, db_request, reason=DisableReason.CompromisedPassword)
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_resets_password_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = UserFactory.create()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.username),
            disable_password=pretend.call_recorder(lambda userid, reason: None),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_reset_password(user, db_request)

        assert db_request.find_service.calls == []
        assert send_email.calls == []
        assert service.disable_password.calls == []
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_reset_password_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_reset_password(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestUserWipeFactors:
    def test_wipes_factors(self, db_request, monkeypatch):
        user = UserFactory.create(
            totp_secret=b"aaaaabbbbbcccccddddd",
            webauthn=[
                WebAuthn(
                    label="fake", credential_id="fake", public_key="extremely fake"
                )
            ],
            recovery_codes=[
                RecoveryCode(code="fake"),
            ],
        )

        assert user.totp_secret is not None
        assert len(user.webauthn) == 1
        assert len(user.recovery_codes.all()) == 1

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = user
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.username),
            disable_password=pretend.call_recorder(
                lambda userid, request, reason: None
            ),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_wipe_factors(user, db_request)

        assert user.totp_secret is None
        assert len(user.webauthn) == 0
        assert len(user.recovery_codes.all()) == 0
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, db_request, reason=DisableReason.CompromisedPassword)
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_wipes_factors_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = UserFactory.create()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user.username),
            disable_password=pretend.call_recorder(lambda userid, reason: None),
        )
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_password_compromised_email", send_email)

        result = views.user_wipe_factors(user, db_request)

        assert db_request.find_service.calls == []
        assert send_email.calls == []
        assert service.disable_password.calls == []
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_wipe_factors_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_wipe_factors(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]


class TestBulkAddProhibitedUserName:
    def test_get(self):
        request = pretend.stub(method="GET")

        assert views.bulk_add_prohibited_user_names(request) == {}

    def test_bulk_add(self, db_request):
        db_request.user = UserFactory.create()
        db_request.method = "POST"

        already_existing_prohibition = ProhibitedUserName(
            name="prohibition-already-exists",
            prohibited_by=db_request.user,
            comment="comment",
        )
        db_request.db.add(already_existing_prohibition)

        already_existing_user = UserFactory.create(username="user-already-exists")
        UserFactory.create(username="deleted-user")

        user_names = [
            already_existing_prohibition.name,
            already_existing_user.username,
            "doesnt-already-exist",
        ]

        db_request.POST["users"] = "\n".join(user_names)

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_user_names/bulk"

        result = views.bulk_add_prohibited_user_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Prohibited {len(user_names)!r} users",
                queue="success",
            )
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/admin/prohibited_user_names/bulk"

        for user_name in user_names:
            prohibition = (
                db_request.db.query(ProhibitedUserName)
                .filter(ProhibitedUserName.name == user_name)
                .one()
            )

            assert prohibition.name == user_name
            assert prohibition.prohibited_by == db_request.user

            assert db_request.db.query(User).filter(User.name == user_name).count() == 0
