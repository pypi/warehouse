# Copyright 2013 Donald Stufft
#
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

from werkzeug.exceptions import NotFound

from warehouse.helpers import url_for
from warehouse.utils import cache, fastly, redirect, render_response


@cache(browser=1, varnish=120)
@fastly("user-profile", "user-profile~{username}")
def user_profile(app, request, username):
    user = app.db.accounts.get_user(username)

    if user is None:
        raise NotFound("Could not find user {}".format(username))

    if user["username"] != username:
        return redirect(
            url_for(
                request,
                "warehouse.accounts.views.user_profile",
                username=user["username"],
            ),
            code=301,
        )

    return render_response(
        app, request, "accounts/profile.html",
        user=user,
        projects=app.db.packaging.get_projects_for_user(user["username"]),
    )
