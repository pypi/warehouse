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

from ...common.db.packaging import UserFactory


class TestManageAccount:
    def test_save_account(self, pyramid_services, user_service, db_request):
        breach_service = pretend.stub()
        pyramid_services.register_service(IUserService, None, user_service)
        pyramid_services.register_service(
            IPasswordBreachedService, None, breach_service
        )
        user = UserFactory.create(name="old name", is_email_private=False)
        db_request.user = user
        db_request.method = "POST"
        db_request.path = "/manage/accounts/"
        db_request.POST = MultiDict({"name": "new name", "is_email_private": "y"})
        views.ManageAccountViews(db_request).save_account()

        user = user_service.get_user(user.id)
        assert user.name == "new name"
        assert user.is_email_private is True
