# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.accounts.models import ProhibitedUserName, User
from warehouse.admin.views import prohibited_user_names as views

from ....common.db.accounts import ProhibitedUsernameFactory, UserFactory


class TestProhibitedUserNameList:
    def test_no_query(self, db_request):
        # `created` is set once per transaction (Postgres `now()`), so every
        # row in this batch shares the same value. Sort by `(created, id)` to
        # match the view's tiebreaker and get a deterministic expected order.
        prohibited = sorted(
            ProhibitedUsernameFactory.create_batch(30),
            key=lambda b: (b.created, b.id),
            reverse=True,
        )

        result = views.prohibited_usernames(db_request)

        assert result == {"prohibited_user_names": prohibited[:25], "query": None}

    def test_with_page(self, db_request):
        prohibited = sorted(
            ProhibitedUsernameFactory.create_batch(30),
            key=lambda b: (b.created, b.id),
            reverse=True,
        )
        db_request.GET["page"] = "2"

        result = views.prohibited_usernames(db_request)

        assert result == {"prohibited_user_names": prohibited[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.prohibited_usernames(request)

    def test_basic_query(self, db_request):
        # A single result, so ordering is irrelevant here.
        target = ProhibitedUsernameFactory.create(name="target-username")
        ProhibitedUsernameFactory.create_batch(29)
        db_request.GET["q"] = target.name

        result = views.prohibited_usernames(db_request)

        assert result == {
            "prohibited_user_names": [target],
            "query": target.name,
        }

    def test_wildcard_query(self, db_request):
        # Use an explicit name so the wildcard can only match this one row,
        # rather than a prefix of a generated username that a sibling row in
        # the batch might also match.
        target = ProhibitedUsernameFactory.create(name="target-username")
        ProhibitedUsernameFactory.create_batch(29)
        db_request.GET["q"] = "target-usernam%"

        result = views.prohibited_usernames(db_request)

        assert result == {
            "prohibited_user_names": [target],
            "query": "target-usernam%",
        }


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
