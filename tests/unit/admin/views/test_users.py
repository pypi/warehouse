# SPDX-License-Identifier: Apache-2.0

import datetime

import freezegun
import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPSeeOther
from sqlalchemy.orm import joinedload
from webob.multidict import MultiDict, NoVars

from warehouse.accounts.interfaces import IEmailBreachedService, IUserService
from warehouse.accounts.models import (
    DisableReason,
    ProhibitedEmailDomain,
    RecoveryCode,
    WebAuthn,
)
from warehouse.admin.views import users as views
from warehouse.observations.models import ObservationKind
from warehouse.packaging.models import JournalEntry, Project, ReleaseURL

from ....common.db.accounts import EmailFactory, User, UserFactory
from ....common.db.packaging import (
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


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
        journal_entries = sorted(
            [JournalEntryFactory.create(submitted_by=user) for _ in range(5)],
            key=lambda j: j.submitted_date,
            reverse=True,
        )
        db_request.matchdict["username"] = str(user.username)
        db_request.POST = NoVars()

        breach_service = pretend.stub(get_email_breach_count=lambda count: 0)
        db_request.find_service = lambda interface, **kwargs: {
            IEmailBreachedService: breach_service,
        }[interface]

        result = views.user_detail(user, db_request)

        assert result["user"] == user
        assert result["roles"] == roles
        assert result["emails_form"].emails[0].primary.data
        assert result["submitted_by_journals"] == journal_entries[:5]
        assert result["user_projects"] == [
            {
                "name": project.name,
                "normalized_name": project.normalized_name,
                "releases_count": 0,
                "total_size": 0,
                "lifecycle_status": None,
                "role_name": "Owner",
            }
        ]

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


class TestUserEmailSubmit:
    def test_updates_user_emails(self, db_request):
        email1 = EmailFactory.create(primary=True)
        email2 = EmailFactory.create(primary=False)
        user = UserFactory.create(emails=[email1, email2])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST["emails-0-email"] = email1.email
        db_request.POST["emails-0-primary"] = False
        db_request.POST["emails-1-email"] = email2.email
        db_request.POST["emails-1-primary"] = True

        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda route_name, username=None: f"/admin/users/{username}/"
        )

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.user_submit_email(user, db_request)

        assert email1.primary is False
        assert email2.primary is True

        assert isinstance(resp, HTTPSeeOther)
        assert resp.headers["Location"] == f"/admin/users/{user.username}/"
        assert db_request.session.flash.calls == [
            pretend.call(f"User '{user.username}': emails updated", queue="success")
        ]

    def test_updates_user_no_primary_email(self, db_request):
        email = EmailFactory.create(primary=True)
        user = UserFactory.create(emails=[email])
        db_request.matchdict["username"] = str(user.username)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST["emails-0-email"] = email.email
        # No primary = checkbox unchecked

        db_request.POST = MultiDict(db_request.POST)
        db_request.route_path = pretend.call_recorder(
            lambda route_name, username=None: f"/admin/users/{username}/"
        )

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.user_submit_email(user, db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.headers["Location"] == f"/admin/users/{user.username}/"
        assert db_request.session.flash.calls == [
            pretend.call(
                "emails: ['There must be exactly one primary email']", queue="error"
            )
        ]

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
        db_request.route_path = pretend.call_recorder(
            lambda route_name, username=None: f"/admin/users/{username}/"
        )

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.user_submit_email(user, db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.headers["Location"] == f"/admin/users/{user.username}/"
        assert db_request.session.flash.calls == [
            pretend.call(
                "emails: ['There must be exactly one primary email']", queue="error"
            )
        ]

    def test_user_detail_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.route_path = pretend.call_recorder(
            lambda route_name, username=None: "/user/the-redirect/"
        )

        result = views.user_submit_email(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

        result = views.user_reset_password(user, db_request)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, db_request, reason=DisableReason.AdminInitiated)
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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

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


class TestUserRecoverAccountInitiate:
    def test_user_recover_account_initiate(self, db_request, db_session):
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
        project0 = ProjectFactory.create()
        RoleFactory.create(user=user, project=project0)
        release0 = ReleaseFactory.create(project=project0)
        db_session.add(
            ReleaseURL(
                release=release0, name="Homepage", url="https://example.com/home0"
            )
        )
        db_session.add(
            ReleaseURL(
                release=release0, name="Source Code", url="http://example.com/source0"
            )
        )
        project1 = ProjectFactory.create()
        RoleFactory.create(user=user, project=project1)
        release1 = ReleaseFactory.create(project=project1)
        db_session.add(
            ReleaseURL(
                release=release1, name="Homepage", url="https://example.com/home1"
            )
        )
        project2 = ProjectFactory.create()
        RoleFactory.create(user=user, project=project2)
        release2 = ReleaseFactory.create(project=project2)
        db_session.add(
            ReleaseURL(release=release2, name="telnet", url="telnet://192.0.2.16:80/")
        )
        project3 = ProjectFactory.create()
        RoleFactory.create(user=user, project=project3)

        result = views.user_recover_account_initiate(user, db_request)

        assert result == {
            "user": user,
            "repo_urls": {
                project0.name: {
                    ("Homepage", "https://example.com/home0"),
                    ("Source Code", "http://example.com/source0"),
                },
                project1.name: {
                    ("Homepage", "https://example.com/home1"),
                },
            },
        }

    def test_user_recover_account_initiate_only_one(self, db_request):
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        admin_user = UserFactory.create()
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
        account_recovery0 = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=admin_user,
            summary="Account Recovery",
            payload={"completed": None},
        )
        account_recovery0.additional = {"status": "initiated"}

        result = views.user_recover_account_initiate(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]

    def test_user_recover_account_initiate_submit(
        self, db_request, db_session, monkeypatch
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(
                release=release, name="Homepage", url="https://example.com/home0"
            )
        )
        db_session.add(
            ReleaseURL(
                release=release, name="Source Code", url="http://example.com/source0"
            )
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_account_recovery_initiated_email", send_email)
        monkeypatch.setattr(views, "token_urlsafe", lambda: "deadbeef")

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = project.name
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/666"
        )
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == [
            pretend.call(
                db_request,
                (user, None),
                project_name=project.name,
                support_issue_link="https://github.com/pypi/support/issues/666",
                token="deadbeef",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert len(user.active_account_recoveries) == 1
        account_recovery = user.active_account_recoveries[0]
        assert account_recovery.payload == {
            "initiated": str(now),
            "completed": None,
            "token": "deadbeef",
            "project_name": project.name,
            "repos": sorted(
                [
                    ("Source Code", "http://example.com/source0"),
                    ("Homepage", "https://example.com/home0"),
                ]
            ),
            "support_issue_link": "https://github.com/pypi/support/issues/666",
            "override_to_email": None,
        }
        assert account_recovery.additional == {"status": "initiated"}

    def test_user_recover_account_initiate_no_urls_submit(
        self, db_request, db_session, monkeypatch
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_account_recovery_initiated_email", send_email)
        monkeypatch.setattr(views, "token_urlsafe", lambda: "deadbeef")

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/666"
        )
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == [
            pretend.call(
                db_request,
                (user, None),
                project_name="",
                support_issue_link="https://github.com/pypi/support/issues/666",
                token="deadbeef",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert len(user.active_account_recoveries) == 1
        account_recovery = user.active_account_recoveries[0]
        assert account_recovery.payload == {
            "initiated": str(now),
            "completed": None,
            "token": "deadbeef",
            "project_name": "",
            "repos": [],
            "support_issue_link": "https://github.com/pypi/support/issues/666",
            "override_to_email": None,
        }
        assert account_recovery.additional == {"status": "initiated"}

    def test_user_recover_account_initiate_override_email(
        self, db_request, db_session, monkeypatch
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_account_recovery_initiated_email", send_email)
        monkeypatch.setattr(views, "token_urlsafe", lambda: "deadbeef")

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/666"
        )
        db_request.POST["override_to_email"] = "foo@example.com"
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_initiate(user, db_request)

        _email = [e for e in user.emails if e.email == "foo@example.com"][0]
        assert _email.verified is False

        assert send_email.calls == [
            pretend.call(
                db_request,
                (user, _email),
                project_name="",
                support_issue_link="https://github.com/pypi/support/issues/666",
                token="deadbeef",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert len(user.active_account_recoveries) == 1
        account_recovery = user.active_account_recoveries[0]
        assert account_recovery.payload == {
            "initiated": str(now),
            "completed": None,
            "token": "deadbeef",
            "project_name": "",
            "repos": [],
            "support_issue_link": "https://github.com/pypi/support/issues/666",
            "override_to_email": "foo@example.com",
        }
        assert account_recovery.additional == {"status": "initiated"}

    def test_user_recover_account_initiate_override_email_exists(
        self, db_request, db_session, monkeypatch
    ):
        admin_user = UserFactory.create()
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
        EmailFactory.create(
            user=user, email="foo@example.com", primary=False, verified=False
        )
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_account_recovery_initiated_email", send_email)
        monkeypatch.setattr(views, "token_urlsafe", lambda: "deadbeef")

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/666"
        )
        db_request.POST["override_to_email"] = "foo@example.com"
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_initiate(user, db_request)

        _email = [e for e in user.emails if e.email == "foo@example.com"][0]
        assert _email.verified is False

        assert send_email.calls == [
            pretend.call(
                db_request,
                (user, _email),
                project_name="",
                support_issue_link="https://github.com/pypi/support/issues/666",
                token="deadbeef",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert len(user.active_account_recoveries) == 1
        account_recovery = user.active_account_recoveries[0]
        assert account_recovery.payload == {
            "initiated": str(now),
            "completed": None,
            "token": "deadbeef",
            "project_name": "",
            "repos": [],
            "support_issue_link": "https://github.com/pypi/support/issues/666",
            "override_to_email": "foo@example.com",
        }
        assert account_recovery.additional == {"status": "initiated"}

    def test_user_recover_account_initiate_override_email_exists_wrong_user(
        self, db_request, db_session, monkeypatch
    ):
        admin_user = UserFactory.create()
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
        other_user = UserFactory.create()
        EmailFactory.create(
            user=other_user, email="foo@example.com", primary=False, verified=False
        )
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_account_recovery_initiated_email", send_email)
        monkeypatch.setattr(views, "token_urlsafe", lambda: "deadbeef")

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/666"
        )
        db_request.POST["override_to_email"] = "foo@example.com"
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.account_recovery.initiate", username=user.username)
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Email address already associated with a user", queue="error")
        ]
        assert len(user.active_account_recoveries) == 0

    def test_user_recover_account_initiate_invalid_email_format(self, db_request):
        user = UserFactory.create()
        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/1"
        )
        db_request.POST["override_to_email"] = "invalid-email"
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_recover_account_initiate(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.session.flash.calls == [
            pretend.call("Invalid or undeliverable email address", queue="error")
        ]

    def test_user_recover_account_initiate_no_support_issue_link_submit(
        self, db_request, db_session
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = ""
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.account_recovery.initiate", username=user.username)
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Provide a link to the pypi/support issue", queue="error")
        ]
        assert len(user.active_account_recoveries) == 0

    def test_user_recover_account_initiate_invalid_support_issue_link_submit(
        self, db_request, db_session
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="telnet", url="telnet://192.0.2.16:80/")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/warehouse/issues/420"
        )
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.account_recovery.initiate", username=user.username)
        ]
        assert db_request.session.flash.calls == [
            pretend.call("The pypi/support issue link is invalid", queue="error")
        ]
        assert len(user.active_account_recoveries) == 0

    def test_recover_account_initiate_invalid_project_name_with_available_urls_submit(
        self, db_request, db_session
    ):
        admin_user = UserFactory.create()
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
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        db_session.add(
            ReleaseURL(release=release, name="Homepage", url="https://example.com/home")
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)

        db_request.method = "POST"
        db_request.user = admin_user
        db_request.POST["project_name"] = ""
        db_request.POST["support_issue_link"] = (
            "https://github.com/pypi/support/issues/420"
        )
        db_request.route_path = pretend.call_recorder(
            lambda route_name, **kwargs: "/user/the-redirect/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_recover_account_initiate(user, db_request)

        assert send_email.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.route_path.calls == [
            pretend.call("admin.user.account_recovery.initiate", username=user.username)
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Select a project for verification", queue="error")
        ]
        assert len(user.active_account_recoveries) == 0


class TestUserRecoverAccountCancel:
    def test_user_recover_account_cancel_cancels_active_account_recoveries(
        self, db_request, monkeypatch
    ):
        admin_user = UserFactory.create()
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

        account_recovery0 = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=admin_user,
            summary="Account Recovery",
            payload={"completed": None},
        )
        account_recovery0.additional = {"status": "initiated"}
        account_recovery1 = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=admin_user,
            summary="Account Recovery",
            payload={"completed": None},
        )
        account_recovery1.additional = {"status": "initiated"}

        assert user.totp_secret is not None
        assert len(user.webauthn) == 1
        assert len(user.recovery_codes.all()) == 1

        db_request.method = "POST"
        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.user = user
        service = pretend.stub()
        db_request.find_service = pretend.call_recorder(lambda iface, context: service)

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_cancel(user, db_request)

        assert user.totp_secret is not None
        assert len(user.webauthn) == 1
        assert len(user.recovery_codes.all()) == 1

        assert db_request.find_service.calls == []
        assert account_recovery0.additional["status"] == "cancelled"
        assert account_recovery0.payload["cancelled"] == str(now)
        assert account_recovery1.additional["status"] == "cancelled"
        assert account_recovery1.payload["cancelled"] == str(now)
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"


class TestUserRecoverAccountComplete:
    def test_user_recover_account_complete(self, db_request, monkeypatch):
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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

        result = views.user_recover_account_complete(user, db_request)

        assert user.totp_secret is None
        assert len(user.webauthn) == 0
        assert len(user.recovery_codes.all()) == 0
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, db_request, reason=DisableReason.AdminInitiated)
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_recover_account_complete_completes_active_account_recoveries(
        self, db_request, monkeypatch
    ):
        admin_user = UserFactory.create()
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

        account_recovery0 = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=admin_user,
            summary="Account Recovery",
            payload={"completed": None},
        )
        account_recovery0.additional = {"status": "initiated"}
        account_recovery1 = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=admin_user,
            summary="Account Recovery",
            payload={"completed": None},
        )
        account_recovery1.additional = {"status": "initiated"}

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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

        now = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(now):
            result = views.user_recover_account_complete(user, db_request)

        assert user.totp_secret is None
        assert len(user.webauthn) == 0
        assert len(user.recovery_codes.all()) == 0
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert account_recovery0.additional["status"] == "completed"
        assert account_recovery0.payload["completed"] == str(now)
        assert account_recovery1.additional["status"] == "completed"
        assert account_recovery1.payload["completed"] == str(now)
        assert send_email.calls == [pretend.call(db_request, user)]
        assert service.disable_password.calls == [
            pretend.call(user.id, db_request, reason=DisableReason.AdminInitiated)
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_recover_account_complete_bad_confirm(self, db_request, monkeypatch):
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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

        result = views.user_recover_account_complete(user, db_request)

        assert db_request.find_service.calls == []
        assert send_email.calls == []
        assert service.disable_password.calls == []
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"

    def test_user_recover_account_complete_redirects_actual_name(self, db_request):
        user = UserFactory.create(username="wu-tang")
        db_request.matchdict["username"] = "Wu-Tang"
        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )

        result = views.user_recover_account_complete(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]

    def test_user_recover_account_complete_with_override_email_sets_as_primary(
        self, db_request, monkeypatch
    ):
        user = UserFactory.create(with_verified_primary_email=True)
        existing_primary_email = user.primary_email

        assert len(user.emails) == 1

        # Create preconditions from `views.user_recover_account_initiate`
        override_to_email = EmailFactory.create(
            user=user, primary=False, verified=False
        )
        recovery_observation = user.record_observation(
            request=db_request,
            kind=ObservationKind.AccountRecovery,
            actor=user,
            summary="Account Recovery",
            payload={
                "initiated": "2021-01-01T00:00:00+00:00",
                "completed": None,
                "override_to_email": override_to_email.email,
            },
        )
        recovery_observation.additional = {"status": "initiated"}

        assert len(user.active_account_recoveries) == 1
        assert len(user.emails) == 2

        db_request.method = "POST"
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
        monkeypatch.setattr(views, "send_password_reset_by_admin_email", send_email)

        result = views.user_recover_account_complete(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/foobar"
        assert existing_primary_email.primary is False
        assert existing_primary_email.verified is True
        assert user.primary_email == override_to_email
        assert user.primary_email.verified is True


class TestUserBurnRecoveryCodes:
    def test_burns_recovery_codes(self, db_request, monkeypatch, user_service):
        user = UserFactory.create()
        codes = user_service.generate_recovery_codes(user.id)
        user_service._check_ratelimits = pretend.call_recorder(
            user_service._check_ratelimits
        )

        # Burn one code in advance
        user.recovery_codes[0].burned = datetime.datetime.now(datetime.UTC)

        # Provide all the codes, plus one invalid code
        db_request.POST["to_burn"] = "\n".join(codes) + "\ninvalid"
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        assert any(not code.burned for code in user.recovery_codes)

        result = views.user_burn_recovery_codes(user, db_request)

        assert all(code.burned for code in user.recovery_codes)
        assert db_request.session.flash.calls == [
            pretend.call("Burned 7 recovery code(s)", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"
        assert user_service._check_ratelimits.calls == []

    def test_no_recovery_codes_provided(self, db_request, monkeypatch, user_service):
        user = UserFactory.create()
        user_service.generate_recovery_codes(user.id)

        db_request.POST["to_burn"] = ""
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        assert all(not code.burned for code in user.recovery_codes)

        result = views.user_burn_recovery_codes(user, db_request)

        assert all(not code.burned for code in user.recovery_codes)
        assert db_request.session.flash.calls == [
            pretend.call("No recovery codes provided", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("admin.user.detail", username=user.username)
        ]
        assert result.status_code == 303
        assert result.location == "/foobar"


class TestUserEmailDomainCheck:
    def test_user_email_domain_check(self, db_request):
        user = UserFactory.create(with_verified_primary_email=True)
        db_request.POST["email_address"] = user.primary_email.email
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_email_domain_check(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Domain status check for '{user.primary_email.domain}' completed",
                queue="success",
            )
        ]
        assert user.primary_email.domain_last_checked is not None
        assert user.primary_email.domain_last_status == ["active"]


class TestUserEmailDelete:
    def test_user_email_delete(self, db_request):
        user = UserFactory.create(with_verified_primary_email=True)
        email = EmailFactory.create(user=user, primary=False, verified=False)

        db_request.POST["email_address"] = email.email
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_email_delete(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(f"Email address '{email.email}' deleted", queue="success")
        ]
        assert email.email not in user.emails

    def test_user_email_delete_not_found(self, db_request):
        user = UserFactory.create(with_verified_primary_email=True)

        db_request.POST["email_address"] = "something@nonexistent.com"
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_email_delete(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call("Email not found", queue="error")
        ]


class TestUserQuarantineProjects:
    def test_quarantines_user_projects(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create()
        project2 = ProjectFactory.create()
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintainer")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Quarantined 2 project(s) for user {user.username!r}",
                queue="success",
            )
        ]
        assert project1.lifecycle_status == "quarantine-enter"
        assert project2.lifecycle_status == "quarantine-enter"

    def test_quarantines_user_projects_skips_already_quarantined(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        project2 = ProjectFactory.create()
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintainer")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Quarantined 1 project(s) for user {user.username!r}",
                queue="success",
            )
        ]
        assert project1.lifecycle_status == "quarantine-enter"
        assert project2.lifecycle_status == "quarantine-enter"

    def test_quarantines_user_projects_no_projects_to_quarantine(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        project2 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintainer")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"No projects needed quarantining for user {user.username!r}",
                queue="info",
            )
        ]

    def test_quarantine_user_projects_bad_confirm(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name="Owner")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda a, **k: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error")
        ]
        assert project.lifecycle_status is None


class TestUserClearQuarantineProjects:
    def test_clears_quarantine_user_projects(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        project2 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintain")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_clear_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Cleared quarantine for 2 project(s) for {user.username!r}",
                queue="success",
            )
        ]
        assert project1.lifecycle_status == "quarantine-exit"
        assert project2.lifecycle_status == "quarantine-exit"

    def test_clears_quarantine_user_projects_skips_non_quarantined(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create()  # Not quarantined
        project2 = ProjectFactory.create(lifecycle_status="quarantine-enter")
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintainer")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_clear_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Cleared quarantine for 1 project(s) for {user.username!r}",
                queue="success",
            )
        ]
        assert project1.lifecycle_status is None
        assert project2.lifecycle_status == "quarantine-exit"

    def test_clears_quarantine_user_projects_no_quarantined_projects(self, db_request):
        user = UserFactory.create()
        project1 = ProjectFactory.create()
        project2 = ProjectFactory.create()
        RoleFactory(project=project1, user=user, role_name="Owner")
        RoleFactory(project=project2, user=user, role_name="Maintainer")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": user.username}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        result = views.user_clear_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"No quarantined projects found for user {user.username!r}",
                queue="info",
            )
        ]

    def test_clear_quarantine_user_projects_bad_confirm(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create(lifecycle_status="quarantine-enter")
        RoleFactory(project=project, user=user, role_name="Owner")

        db_request.matchdict["username"] = str(user.username)
        db_request.params = {"username": "wrong"}
        db_request.route_path = pretend.call_recorder(lambda a, **k: "/foobar")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.user_clear_quarantine_projects(user, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foobar"
        assert db_request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error")
        ]
        assert project.lifecycle_status == "quarantine-enter"
