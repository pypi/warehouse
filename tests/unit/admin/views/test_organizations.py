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

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.accounts.interfaces import IUserService
from warehouse.admin.views import organizations as views
from warehouse.organizations.interfaces import IOrganizationService

from ....common.db.organizations import OrganizationFactory


class TestOrganizationList:
    def test_no_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(30)],
            key=lambda o: o.normalized_name,
        )
        result = views.organization_list(db_request)

        assert result == {"organizations": organizations[:25], "query": "", "terms": []}

    def test_with_page(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(30)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["page"] = "2"
        result = views.organization_list(db_request)

        assert result == {"organizations": organizations[25:], "query": "", "terms": []}

    def test_with_invalid_page(self, enable_organizations):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            params={"page": "not an integer"},
        )

        with pytest.raises(HTTPBadRequest):
            views.organization_list(request)

    def test_basic_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = organizations[0].name
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [organizations[0]],
            "query": organizations[0].name,
            "terms": [organizations[0].name],
        }

    def test_name_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"name:{organizations[0].name}"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [organizations[0]],
            "query": f"name:{organizations[0].name}",
            "terms": [f"name:{organizations[0].name}"],
        }

    def test_organization_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"organization:{organizations[0].display_name}"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [organizations[0]],
            "query": f"organization:{organizations[0].display_name}",
            "terms": [f"organization:{organizations[0].display_name}"],
        }

    def test_url_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"url:{organizations[0].link_url}"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [organizations[0]],
            "query": f"url:{organizations[0].link_url}",
            "terms": [f"url:{organizations[0].link_url}"],
        }

    def test_description_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = f"description:'{organizations[0].description}'"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": [organizations[0]],
            "query": f"description:'{organizations[0].description}'",
            "terms": [f"description:{organizations[0].description}"],
        }

    def test_is_approved_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_approved = True
        organizations[1].is_approved = True
        organizations[2].is_approved = False
        organizations[3].is_approved = None
        organizations[4].is_approved = None
        db_request.GET["q"] = "is:approved"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[:2],
            "query": "is:approved",
            "terms": ["is:approved"],
        }

    def test_is_declined_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_approved = True
        organizations[1].is_approved = True
        organizations[2].is_approved = False
        organizations[3].is_approved = None
        organizations[4].is_approved = None
        db_request.GET["q"] = "is:declined"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[2:3],
            "query": "is:declined",
            "terms": ["is:declined"],
        }

    def test_is_submitted_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_approved = True
        organizations[1].is_approved = True
        organizations[2].is_approved = False
        organizations[3].is_approved = None
        organizations[4].is_approved = None
        db_request.GET["q"] = "is:submitted"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[3:],
            "query": "is:submitted",
            "terms": ["is:submitted"],
        }

    def test_is_active_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_active = True
        organizations[1].is_active = True
        organizations[2].is_active = False
        organizations[3].is_active = False
        organizations[4].is_active = False
        db_request.GET["q"] = "is:active"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[:2],
            "query": "is:active",
            "terms": ["is:active"],
        }

    def test_is_inactive_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        organizations[0].is_active = True
        organizations[1].is_active = True
        organizations[2].is_active = False
        organizations[3].is_active = False
        organizations[4].is_active = False
        db_request.GET["q"] = "is:inactive"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[2:],
            "query": "is:inactive",
            "terms": ["is:inactive"],
        }

    def test_is_invalid_query(self, enable_organizations, db_request):
        organizations = sorted(
            [OrganizationFactory.create() for _ in range(5)],
            key=lambda o: o.normalized_name,
        )
        db_request.GET["q"] = "is:not-actually-a-valid-query"
        result = views.organization_list(db_request)

        assert result == {
            "organizations": organizations[:25],
            "query": "is:not-actually-a-valid-query",
            "terms": ["is:not-actually-a-valid-query"],
        }

    def test_disable_organizations(self, db_request):
        with pytest.raises(HTTPNotFound):
            views.organization_list(db_request)


class TestOrganizationDetail:
    def test_detail(self, enable_organizations):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        create_event = pretend.stub(
            additional={"created_by_user_id": str(user.id)},
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            is_approved=None,
            events=pretend.stub(
                filter=lambda *a, **kw: pretend.stub(
                    order_by=lambda *a, **kw: pretend.stub(
                        first=lambda *a, **kw: create_event,
                    ),
                ),
            ),
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "admin": None,
            "user": user,
            "organization": organization,
        }

    def test_detail_is_approved_true(self, enable_organizations):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        create_or_approve_event = pretend.stub(
            additional={
                "created_by_user_id": str(user.id),
                "approved_by_user_id": str(admin.id),
            },
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=True,
            is_approved=True,
            events=pretend.stub(
                filter=lambda *a, **kw: pretend.stub(
                    order_by=lambda *a, **kw: pretend.stub(
                        first=lambda *a, **kw: create_or_approve_event,
                    ),
                ),
            ),
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "admin": admin,
            "user": user,
            "organization": organization,
        }

    def test_detail_is_approved_false(self, enable_organizations):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        create_or_decline_event = pretend.stub(
            additional={
                "created_by_user_id": str(user.id),
                "declined_by_user_id": str(admin.id),
            },
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            is_approved=False,
            events=pretend.stub(
                filter=lambda *a, **kw: pretend.stub(
                    order_by=lambda *a, **kw: pretend.stub(
                        first=lambda *a, **kw: create_or_decline_event,
                    ),
                ),
            ),
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.organization_detail(request) == {
            "admin": admin,
            "user": user,
            "organization": organization,
        }

    def test_detail_not_found(self, enable_organizations):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_detail(request)

    def test_approve(self, enable_organizations, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admins=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        create_event = pretend.stub(
            additional={"created_by_user_id": str(user.id)},
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            is_approved=None,
            events=pretend.stub(
                filter=lambda *a, **kw: pretend.stub(
                    order_by=lambda *a, **kw: pretend.stub(
                        first=lambda *a, **kw: create_event,
                    ),
                ),
            ),
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
            approve_organization=pretend.call_recorder(lambda *a, **kw: None),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        message = pretend.stub()
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": organization.id},
            params={"organization_name": organization.name, "message": message},
            route_path=lambda *a, **kw: organization_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            user=admin,
        )
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_approved_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_approved_email", send_email)

        result = views.organization_approve(request)

        assert organization_service.approve_organization.calls == [
            pretend.call(organization.id),
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:approve",
                additional={"approved_by_user_id": str(admin.id)},
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization.name}" organization approved',
                queue="success",
            ),
        ]
        assert send_email.calls == [
            pretend.call(
                request,
                [admin],
                organization_name=organization.name,
                initiator_username=user.username,
                message=message,
            ),
            pretend.call(
                request,
                user,
                organization_name=organization.name,
                message=message,
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_approve_wrong_confirmation_input(self, enable_organizations, monkeypatch):
        user_service = pretend.stub()
        organization = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": organization.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_approve(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_approve_not_found(self, enable_organizations):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_approve(request)

    def test_decline(self, enable_organizations, monkeypatch):
        admin = pretend.stub(
            id="admin-id",
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            id="user-id",
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admins=lambda *a, **kw: [admin],
            get_user=lambda userid, **kw: {admin.id: admin, user.id: user}[userid],
        )
        create_event = pretend.stub(
            additional={"created_by_user_id": str(user.id)},
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            is_approved=None,
            events=pretend.stub(
                filter=lambda *a, **kw: pretend.stub(
                    order_by=lambda *a, **kw: pretend.stub(
                        first=lambda *a, **kw: create_event,
                    ),
                ),
            ),
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
            decline_organization=pretend.call_recorder(lambda *a, **kw: None),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        message = pretend.stub()
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": organization.id},
            params={"organization_name": organization.name, "message": message},
            route_path=lambda *a, **kw: organization_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            user=admin,
        )
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_declined_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_declined_email", send_email)

        result = views.organization_decline(request)

        assert organization_service.decline_organization.calls == [
            pretend.call(organization.id),
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:decline",
                additional={"declined_by_user_id": str(admin.id)},
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Request for "{organization.name}" organization declined',
                queue="success",
            ),
        ]
        assert send_email.calls == [
            pretend.call(
                request,
                [admin],
                organization_name=organization.name,
                initiator_username=user.username,
                message=message,
            ),
            pretend.call(
                request,
                user,
                organization_name=organization.name,
                message=message,
            ),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_decline_wrong_confirmation_input(self, enable_organizations, monkeypatch):
        user_service = pretend.stub()
        organization = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda iface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            matchdict={"organization_id": organization.id},
            params={"organization_name": pretend.stub()},
            route_path=lambda *a, **kw: organization_detail_location,
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
        )

        result = views.organization_decline(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_decline_not_found(self, enable_organizations):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.organization_decline(request)

    def test_detail_disable_organizations(self, db_request):
        with pytest.raises(HTTPNotFound):
            views.organization_detail(db_request)

    def test_approve_disable_organizations(self, db_request):
        with pytest.raises(HTTPNotFound):
            views.organization_approve(db_request)

    def test_decline_disable_organizations(self, db_request):
        with pytest.raises(HTTPNotFound):
            views.organization_decline(db_request)
