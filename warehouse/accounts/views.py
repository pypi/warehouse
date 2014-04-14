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
from flask import (
    Blueprint, request, url_for, render_template, redirect,
    current_app as app, session
)
from werkzeug.exceptions import NotFound

from warehouse import fastly
from warehouse.accounts.forms import LoginForm
from warehouse.csrf import csrf_cycle, csrf_protect
from warehouse.sessions import uses_session
from warehouse.utils import cache, redirect_next

blueprint = Blueprint('warehouse.accounts.views', __name__)


@blueprint.route('/user/<username>', methods=["GET"])
@cache(browser=1, varnish=120)
@fastly.users
def user_profile(username):
    user = app.db.accounts.get_user(username)

    if user is None:
        raise NotFound("Could not find user {}".format(username))

    if user["username"] != username:
        return redirect(
            url_for(
                "warehouse.accounts.views.user_profile",
                username=user["username"],
            ),
            code=301,
        )

    return render_template(
        "accounts/profile.html",
        user=user,
        projects=app.db.packaging.get_projects_for_user(user["username"]),
    )


@blueprint.route('/account/login', methods=["GET", "POST"])
@csrf_protect
@uses_session
def login():
    form = LoginForm(
        request.form,
        authenticator=app.db.accounts.user_authenticate,
        translations=app.translations,
    )

    if request.method == "POST" and form.validate():
        # Get the user's ID, this is what we will use as the identifier anytime
        # we need to securely reference the user within the database.
        user_id = app.db.accounts.get_user_id(form.username.data)

        if session.get("user.id") != user_id:
            # To avoid reusing another user's session data, clear the session
            # data if the existing session corresponds to a different
            # authenticated user.
            session.clear()

        # Cycle the session key to prevent session fixation attacks from
        # crossing an authentication boundary
        session.cycle()

        # Cycle the CSRF token to prevent a CSRF via session fixation attack
        # from crossing an authentication boundary
        csrf_cycle(session)

        # Log the user in by storing their user id in their session
        session["user.id"] = user_id

        # We'll want to redirect the user with a 303 once we've completed the
        # log in process.
        resp = redirect_next(
            default=url_for("warehouse.views.index"),
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
    return render_template(
        "accounts/login.html",
        form=form,
        next=request.values.get("next"),
    )


@blueprint.route('/account/logout/', methods=["GET", "POST"])
@csrf_protect
@uses_session
def logout():
    if request.method == "POST":
        # Delete our session, the user is logging out and we no longer want it
        session.delete()

        # We'll want to redirect the user with a 303 once we've completed the
        # log in process.
        resp = redirect_next(
            default=url_for("warehouse.views.index"),
        )

        # Delete the username cookie, the user is logging out and we no longer
        # want to store the username that they used when they were logged in.
        resp.delete_cookie("username")

        # Return our prepared response to the now logged out user
        return resp

    # This is a simple GET request, so we just want to render the template
    return render_template(
        "accounts/logout.html", next=request.values.get("next"),
    )
