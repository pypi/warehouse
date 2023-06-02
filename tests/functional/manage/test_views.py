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
from warehouse.manage import views
from warehouse.manage.views import organizations as org_views
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
        enable_organizations,
        monkeypatch,
    ):
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            organization_service, IOrganizationService, None
        )
        user = UserFactory.create(name="old name")
        EmailFactory.create(primary=True, verified=True, public=True, user=user)
        db_request.user = user
        db_request.organization_access = True
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
        db_request.registry.settings[
            "warehouse.organizations.max_undecided_organization_applications"
        ] = 3
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_new_organization_requested_email", send_email
        )

        org_views.ManageOrganizationsViews(db_request).create_organization_application()
        organization_application = (
            organization_service.get_organization_applications_by_name(
                db_request.POST["name"]
            )
        )[0]

        assert organization_application.name == db_request.POST["name"]
        assert organization_application.display_name == db_request.POST["display_name"]
        assert (
            organization_application.orgtype
            == OrganizationType[db_request.POST["orgtype"]]
        )
        assert organization_application.link_url == db_request.POST["link_url"]
        assert organization_application.description == db_request.POST["description"]
        assert organization_application.submitted_by == user
