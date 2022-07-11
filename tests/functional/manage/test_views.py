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

from webob.multidict import MultiDict

from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.admin.flags import AdminFlagValue
from warehouse.manage import views
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import OrganizationType

from ...common.db.accounts import EmailFactory, UserFactory


class TestManageAccount:
    def test_save_account(self, pyramid_services, user_service, db_request):
        breach_service = pretend.stub()
        organization_service = pretend.stub()
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )
        pyramid_services.register_service(
            organization_service, IOrganizationService, None
        )
        user = UserFactory.create(name="old name")
        EmailFactory.create(primary=True, verified=True, public=True, user=user)
        db_request.user = user
        db_request.method = "POST"
        db_request.path = "/manage/accounts/"
        db_request.POST = MultiDict({"name": "new name", "public_email": ""})

        views.ManageAccountViews(db_request).save_account()
        user = user_service.get_user(user.id)

        assert user.name == "new name"
        assert user.public_email is None


class TestManageOrganizations:
    def test_create_organization(
        self,
        pyramid_services,
        user_service,
        organization_service,
        db_request,
        monkeypatch,
    ):
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            organization_service, IOrganizationService, None
        )
        user = UserFactory.create(name="old name")
        EmailFactory.create(primary=True, verified=True, public=True, user=user)
        db_request.user = user
        db_request.method = "POST"
        db_request.path = "/manage/organizations/"
        db_request.POST = MultiDict(
            {
                "name": "psf",
                "display_name": "Python Software Foundation",
                "orgtype": "Community",
                "link_url": "https://www.python.org/psf/",
                "description": (
                    "To promote, protect, and advance the Python programming "
                    "language, and to support and facilitate the growth of a "
                    "diverse and international community of Python programmers"
                ),
            }
        )
        monkeypatch.setattr(
            db_request,
            "flags",
            pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
        )
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_requested_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_requested_email", send_email)

        views.ManageOrganizationsViews(db_request).create_organization()
        organization = organization_service.get_organization_by_name(
            db_request.POST["name"]
        )

        assert db_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS),
        ]
        assert organization.name == db_request.POST["name"]
        assert organization.display_name == db_request.POST["display_name"]
        assert organization.orgtype == OrganizationType[db_request.POST["orgtype"]]
        assert organization.link_url == db_request.POST["link_url"]
        assert organization.description == db_request.POST["description"]
