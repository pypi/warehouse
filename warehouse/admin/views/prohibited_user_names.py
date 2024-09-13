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

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import literal

from warehouse.accounts.models import ProhibitedUserName, User
from warehouse.admin.views.users import _nuke_user
from warehouse.authnz import Permissions


@view_config(
    route_name="admin.prohibited_user_names.bulk_add",
    renderer="admin/prohibited_user_names/bulk.html",
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_methods=False,
)
def bulk_add_prohibited_user_names(request):
    if request.method == "POST":
        user_names = request.POST.get("users", "").split()

        for user_name in user_names:
            # Check to make sure the prohibition doesn't already exist.
            if (
                request.db.query(literal(True))
                .filter(
                    request.db.query(ProhibitedUserName)
                    .filter(ProhibitedUserName.name == user_name.lower())
                    .exists()
                )
                .scalar()
            ):
                continue

            # Go through and delete the usernames

            user = request.db.query(User).filter(User.username == user_name).first()
            if user is not None:
                _nuke_user(user, request)
            else:
                request.db.add(
                    ProhibitedUserName(
                        name=user_name.lower(),
                        comment="nuked",
                        prohibited_by=request.user,
                    )
                )

        request.session.flash(f"Prohibited {len(user_names)!r} users", queue="success")

        return HTTPSeeOther(request.route_path("admin.prohibited_user_names.bulk_add"))
    return {}
