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

from warehouse.accounts.forms import LoginForm
from warehouse.helpers import url_for
from warehouse.utils import (
    cache, fastly, redirect, render_response, uses_session,
)


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

# TODO: CSRF
# TODO: Allow a ?next=url


@uses_session
def login(app, request):
    form = LoginForm(
        request.form,
        authenticator=app.db.accounts.user_authenticate,
    )

    if request.method == "POST" and form.validate():
        # Get the user's ID, this is what we will use as the identifier anytime
        # we need to securely reference the user within the database.
        user_id = app.db.accounts.get_user_id(form.username.data)

        if request.session.get("user.id") != user_id:
            # To avoid reusing another user's session data, clear the session
            # data if the existing session corresponds to a different
            # authenticated user.
            request.session.clear()

        # Cycle the session key to prevent session fixation attacks from
        # crossing an authentication boundary
        request.session.cycle()

        # Log the user in by storing their user id in their session
        request.session["user.id"] = user_id

        # We'll want to redirect the user with a 303 once we've completed the
        # log in process.
        resp = redirect(url_for(request, "warehouse.views.index"), code=303)

        # Store the user's name in a cookie so that the client side can use
        # it for display purposes. This value **MUST** not be used for any
        # sort of access control.
        resp.set_cookie("username", form.username.data)

        # Return our prepared response to the user
        return resp

    # Either this is a GET request or it is a POST request with a failing form
    # validation. Either way we want to simply render our template with the
    # form available.
    return render_response(
        app, request, "accounts/login.html",
        form=form,
    )
