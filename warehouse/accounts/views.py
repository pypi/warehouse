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

from pyramid.httpexceptions import (
    HTTPMovedPermanently, HTTPNotFound, HTTPSeeOther,
)
from pyramid.security import remember, forget
from pyramid.view import view_config

from warehouse.accounts.forms import LoginForm
from warehouse.accounts.models import User
from warehouse.cache.http import cache_control, surrogate_control
from warehouse.csrf import csrf_protect
from warehouse.sessions import uses_session


@view_config(
    route_name="accounts.profile",
    renderer="accounts/profile.html",
    decorator=[
        cache_control(1 * 24 * 60 * 60),       # 1 day
        surrogate_control(30 * 24 * 60 * 60),  # 30 days
    ],
)
def profile(request, username):
    user = request.db.query(User).filter(User.username == username).first()

    if user is None:
        raise HTTPNotFound("Could not find user {}".format(username))

    if user.username != username:
        return HTTPMovedPermanently(
            request.current_route_url(username=user.username),
        )

    return {"user": user}


@view_config(
    route_name="accounts.login",
    renderer="accounts/login.html",
    decorator=[csrf_protect("accounts.login"), uses_session],
)
def login(request, _form_class=LoginForm):
    # TODO: If already logged in just redirect to ?next=
    # TODO: Logging in should reset request.user
    # TODO: Prevent session fixation:
    #       https://github.com/Pylons/pyramid/pull/1570
    # TODO: Configure the login view as the default view for not having
    #       permission to view something.

    form = _form_class(
        request.POST,
        db=request.db,
        password_hasher=request.password_hasher,
    )

    if request.method == "POST" and form.validate():
        # Remember the userid using the authentication policy.
        headers = remember(request, form.user.id)
        request.response.headerlist.extend(headers)

        # Cycle the CSRF token since we've crossed an authentication boundary
        # and we don't want to continue using the old one.
        request.session.new_csrf_token()

        # Now that we're logged in we'll want to redirect the user to either
        # where they were trying to go originally, or to the default view.
        # TODO: Implement ?next= support.
        # TODO: Figure out a better way to handle the "default view".
        return HTTPSeeOther("/")

    return {"form": form}


@view_config(
    route_name="accounts.logout",
    renderer="accounts/logout.html",
    decorator=[csrf_protect("accounts.logout"), uses_session],
)
def logout(request):
    # TODO: If already logged out just redirect to ?next=
    # TODO: Logging out should reset request.user
    # TODO: Prevent session fixation:
    #       https://github.com/Pylons/pyramid/pull/1570

    if request.method == "POST":
        # A POST to the logout view tells us to logout. There's no form to
        # validate here becuse there's no data. We should be protected against
        # CSRF attacks still because of the CSRF framework, so users will still
        # need a post body that contains the CSRF token.
        headers = forget(request)
        request.response.headerlist.extend(headers)

        # Now that we're logged out we'll want to redirect the user to either
        # where they were originally, or to the default view.
        # TODO: Implement ?next= support.
        # TODO: Figure out a better way to handle the "default view".
        return HTTPSeeOther("/")

    return {}
