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

from pyramid.httpexceptions import HTTPNotFound

from warehouse.accounts.interfaces import IUserService
from warehouse.admin.views import organizations as views
from warehouse.organizations.interfaces import IOrganizationService


class TestOrganizations:
    def test_detail(self):
        user = pretend.stub(
            username="example",
            name="Example",
            public_email="webmaster@example.com",
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
            users=[user],
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.detail(request) == {
            "user": user,
            "organization": organization,
        }

    def test_detail_not_found(self):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.detail(request)

    def test_approve(self, monkeypatch):
        admin = pretend.stub(
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admins=lambda *a, **kw: [admin],
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
            users=[user],
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
            approve_organization=pretend.call_recorder(lambda *a, **kw: None),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        message = pretend.stub()
        request = pretend.stub(
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

        result = views.approve(request)

        assert organization_service.approve_organization.calls == [
            pretend.call(organization.id),
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:approve",
                additional={"approved_by": admin.username},
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

    def test_approve_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
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

        result = views.approve(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_approve_not_found(self):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.approve(request)

    def test_decline(self, monkeypatch):
        admin = pretend.stub(
            username="admin",
            name="Admin",
            public_email="admin@pypi.org",
        )
        user = pretend.stub(
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        user_service = pretend.stub(
            get_admins=lambda *a, **kw: [admin],
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
            users=[user],
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
            decline_organization=pretend.call_recorder(lambda *a, **kw: None),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        message = pretend.stub()
        request = pretend.stub(
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

        result = views.decline(request)

        assert organization_service.decline_organization.calls == [
            pretend.call(organization.id),
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:decline",
                additional={"declined_by": admin.username},
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

    def test_decline_wrong_confirmation_input(self, monkeypatch):
        user_service = pretend.stub()
        organization = pretend.stub(id=pretend.stub(), name=pretend.stub())
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
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

        result = views.decline(request)

        assert request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error"),
        ]
        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_decline_not_found(self):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.decline(request)
