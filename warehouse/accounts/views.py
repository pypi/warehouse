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
from warehouse.csrf import csrf_cycle, csrf_protect
from warehouse.helpers import url_for
from warehouse.sessions import uses_session
from warehouse.utils import (
    cache, fastly, redirect, redirect_next, render_response,
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


@csrf_protect
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

        # Cycle the CSRF token to prevent a CSRF via session fixation attack
        # from crossing an authentication boundary
        csrf_cycle(request.session)

        # Log the user in by storing their user id in their session
        request.session["user.id"] = user_id

        # We'll want to redirect the user with a 303 once we've completed the
        # log in process.
        resp = redirect_next(
            request,
            default=url_for(request, "warehouse.views.index"),
        )

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
        next=request.values.get("next"),
    )


@csrf_protect
@uses_session
def logout(app, request):
    if request.method == "POST":
        # Delete our session, the user is logging out and we no longer want it
        request.session.delete()

        # We'll want to redirect the user with a 303 once we've completed the
        # log in process.
        resp = redirect_next(
            request,
            default=url_for(request, "warehouse.views.index"),
        )

        # Delete the username cookie, the user is logging out and we no longer
        # want to store the username that they used when they were logged in.
        resp.delete_cookie("username")

        # Return our prepared response to the now logged out user
        return resp

    # This is a simple GET request, so we just want to render the template
    return render_response(
        app, request, "accounts/logout.html",
        next=request.values.get("next"),
    )
