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

from warehouse.accounts.models import ProhibitedUserName, User
from warehouse.admin.views import prohibited_user_names as views

from ....common.db.accounts import UserFactory


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
