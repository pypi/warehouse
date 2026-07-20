# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import project_size_limit_requests as views
from warehouse.packaging.models import ProjectSizeLimitRequestStatus

from ....common.db.accounts import UserFactory
from ....common.db.packaging import ProjectFactory, ProjectSizeLimitRequestFactory


class TestProjectSizeLimitRequestsList:
    def test_list(self, db_request):
        older = ProjectSizeLimitRequestFactory.create(
            submitted=datetime.datetime(2021, 1, 1)
        )
        newer = ProjectSizeLimitRequestFactory.create(
            submitted=datetime.datetime(2021, 6, 1)
        )

        result = views.project_size_limit_requests_list(db_request)

        assert result["project_size_limit_requests"][0].id == newer.id
        assert result["project_size_limit_requests"][1].id == older.id


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
    def test_approve(self, db_request):
        project = ProjectFactory.create(name="foo")
        user = UserFactory.create()
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            project=project,
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

        result = views.project_size_limit_request_approve(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert project.total_size_limit == 150 * (1024**3)
        assert size_limit_request.status == ProjectSizeLimitRequestStatus.Approved
        assert size_limit_request.admin_message == "Looks good"

        tags = {event.tag for event in project.events}
        assert "admin:project:set_total_size_limit" in tags
        assert "admin:project:size_limit_request:approved" in tags

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


class TestProjectSizeLimitRequestDecline:
    def test_decline(self, db_request):
        project = ProjectFactory.create(name="foo")
        user = UserFactory.create()
        size_limit_request = ProjectSizeLimitRequestFactory.create(
            project=project, status=ProjectSizeLimitRequestStatus.Submitted
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

        result = views.project_size_limit_request_decline(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert project.total_size_limit == old_total_size_limit
        assert size_limit_request.status == ProjectSizeLimitRequestStatus.Declined
        assert size_limit_request.admin_message == "Not eligible"

        tags = {event.tag for event in project.events}
        assert "admin:project:size_limit_request:declined" in tags

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
