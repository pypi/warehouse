# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import project_size_limit_requests as views
from warehouse.packaging.models import ProjectSizeLimitRequestStatus

from ....common.db.accounts import UserFactory
from ....common.db.packaging import ProjectFactory, ProjectSizeLimitRequestFactory


class TestProjectSizeLimitRequestsList:
    def test_no_query(self, db_request):
        older = ProjectSizeLimitRequestFactory.create(
            submitted=datetime.datetime(2021, 1, 1)
        )
        newer = ProjectSizeLimitRequestFactory.create(
            submitted=datetime.datetime(2021, 6, 1)
        )

        result = views.project_size_limit_requests_list(db_request)

        assert result["project_size_limit_requests"][0].id == newer.id
        assert result["project_size_limit_requests"][1].id == older.id
        assert result["query"] == ""
        assert result["terms"] == []

    def test_basic_query(self, db_request):
        project = ProjectFactory.create(name="findable-project")
        match = ProjectSizeLimitRequestFactory.create(project=project)
        ProjectSizeLimitRequestFactory.create()

        db_request.GET["q"] = "findable-project"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [match.id]
        assert result["query"] == "findable-project"
        assert result["terms"] == ["findable-project"]

    def test_project_query(self, db_request):
        project = ProjectFactory.create(name="findable-project")
        match = ProjectSizeLimitRequestFactory.create(project=project)
        ProjectSizeLimitRequestFactory.create()

        db_request.GET["q"] = "project:findable-project"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [match.id]

    def test_by_query(self, db_request):
        user = UserFactory.create(username="findable-user")
        match = ProjectSizeLimitRequestFactory.create(submitted_by=user)
        ProjectSizeLimitRequestFactory.create()

        db_request.GET["q"] = "by:findable-user"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [match.id]

    def test_is_submitted_query(self, db_request):
        submitted = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Submitted
        )
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Approved
        )
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Declined
        )

        db_request.GET["q"] = "is:submitted"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [submitted.id]

    def test_is_approved_query(self, db_request):
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Submitted
        )
        approved = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Approved
        )
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Declined
        )

        db_request.GET["q"] = "is:approved"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [approved.id]

    def test_is_declined_query(self, db_request):
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Submitted
        )
        ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Approved
        )
        declined = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Declined
        )

        db_request.GET["q"] = "is:declined"
        result = views.project_size_limit_requests_list(db_request)

        assert [r.id for r in result["project_size_limit_requests"]] == [declined.id]

    def test_is_invalid_query(self, db_request):
        ProjectSizeLimitRequestFactory.create_batch(3)

        db_request.GET["q"] = "is:not-actually-a-valid-query"
        result = views.project_size_limit_requests_list(db_request)

        # An unrecognized `is:` value falls back to a plain keyword search
        # instead of silently matching everything.
        assert len(result["project_size_limit_requests"]) == 0

    def test_invalid_query(self, db_request):
        db_request.GET["q"] = 'foo"'

        with pytest.raises(HTTPBadRequest):
            views.project_size_limit_requests_list(db_request)

    def test_invalid_page(self, db_request):
        db_request.GET["page"] = "not-a-number"

        with pytest.raises(HTTPBadRequest):
            views.project_size_limit_requests_list(db_request)


class TestProjectSizeLimitRequestDetail:
    def test_detail(self, db_request):
        size_limit_request = ProjectSizeLimitRequestFactory.create()
        db_request.matchdict["request_id"] = str(size_limit_request.id)

        result = views.project_size_limit_request_detail(db_request)

        assert result["size_limit_request"].id == size_limit_request.id

    def test_not_found(self, db_request):
        db_request.matchdict["request_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.project_size_limit_request_detail(db_request)


class TestProjectSizeLimitRequestApprove:
    def test_approve(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")
        user = UserFactory.create()
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            project=project,
            submitted_by=user,
            requested_limit=150 * (1024**3),
            status=ProjectSizeLimitRequestStatus.Submitted,
        )

        db_request.matchdict["request_id"] = str(size_limit_request.id)
        db_request.method = "POST"
        db_request.params = {"message": "Looks good"}
        db_request.user = user
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_project_size_limit_request_approved_email", send_email
        )

        result = views.project_size_limit_request_approve(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert project.total_size_limit == 150 * (1024**3)
        assert size_limit_request.status == ProjectSizeLimitRequestStatus.Approved
        assert size_limit_request.admin_message == "Looks good"

        tags = {event.tag for event in project.events}
        assert "admin:project:set_total_size_limit" in tags
        assert "admin:project:size_limit_request:approved" in tags

        assert send_email.calls == [
            pretend.call(
                db_request,
                user,
                project_name="foo",
                requested_limit=150 * (1024**3),
                message="Looks good",
            )
        ]

    def test_approve_not_found(self, db_request):
        db_request.matchdict["request_id"] = str(uuid.uuid4())
        db_request.method = "POST"

        with pytest.raises(HTTPNotFound):
            views.project_size_limit_request_approve(db_request)

    def test_approve_already_reviewed(self, db_request):
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Approved
        )

        db_request.matchdict["request_id"] = str(size_limit_request.id)
        db_request.method = "POST"
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.project_size_limit_request_approve(db_request)

        assert exc.value.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("This request has already been reviewed", queue="error")
        ]

    def test_approve_message_too_long(self, db_request):
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Submitted
        )

        db_request.matchdict["request_id"] = str(size_limit_request.id)
        db_request.method = "POST"
        db_request.params = {"message": "x" * 4097}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.project_size_limit_request_approve(db_request)

        assert exc.value.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Message must be 4096 characters or less", queue="error")
        ]
        assert size_limit_request.status == ProjectSizeLimitRequestStatus.Submitted


class TestProjectSizeLimitRequestDecline:
    def test_decline(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")
        user = UserFactory.create()
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            project=project,
            submitted_by=user,
            status=ProjectSizeLimitRequestStatus.Submitted,
        )
        old_total_size_limit = project.total_size_limit

        db_request.matchdict["request_id"] = str(size_limit_request.id)
        db_request.method = "POST"
        db_request.params = {"message": "Not eligible"}
        db_request.user = user
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_project_size_limit_request_declined_email", send_email
        )

        result = views.project_size_limit_request_decline(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert project.total_size_limit == old_total_size_limit
        assert size_limit_request.status == ProjectSizeLimitRequestStatus.Declined
        assert size_limit_request.admin_message == "Not eligible"

        tags = {event.tag for event in project.events}
        assert "admin:project:size_limit_request:declined" in tags

        assert send_email.calls == [
            pretend.call(
                db_request,
                user,
                project_name="foo",
                message="Not eligible",
            )
        ]

    def test_decline_not_found(self, db_request):
        db_request.matchdict["request_id"] = str(uuid.uuid4())
        db_request.method = "POST"

        with pytest.raises(HTTPNotFound):
            views.project_size_limit_request_decline(db_request)

    def test_decline_already_reviewed(self, db_request):
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            status=ProjectSizeLimitRequestStatus.Declined
        )

        db_request.matchdict["request_id"] = str(size_limit_request.id)
        db_request.method = "POST"
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.project_size_limit_request_decline(db_request)

        assert exc.value.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("This request has already been reviewed", queue="error")
        ]
