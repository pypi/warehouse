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

from ...common.db.accounts import EmailFactory, UserFactory


class TestManageAccount:
    def test_save_account(self, pyramid_services, user_service, db_request):
        breach_service = pretend.stub()
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
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
