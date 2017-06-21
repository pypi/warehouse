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

import datetime

from pyblake2 import blake2b
from pyramid.httpexceptions import (
    HTTPMovedPermanently, HTTPSeeOther, HTTPTooManyRequests,
)
from pyramid.security import remember, forget
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts import forms
from warehouse.accounts.interfaces import IUserService, TooManyFailedLogins
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release
from warehouse.utils.http import is_safe_url


USER_ID_INSECURE_COOKIE = "user_id__insecure"


@view_config(context=TooManyFailedLogins)
def failed_logins(exc, request):
    resp = HTTPTooManyRequests(
        "There have been too many unsuccessful login attempts. Please try "
        "again later.",
        retry_after=exc.resets_in.total_seconds(),
    )

    # TODO: This is kind of gross, but we need it for as long as the legacy
    #       upload API exists and is supported. Once we get rid of that we can
    #       get rid of this as well.
    resp.status = "{} {}".format(
        resp.status_code,
        "Too Many Failed Login Attempts",
    )

    return resp


@view_config(
    route_name="accounts.profile",
    renderer="accounts/profile.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,                 # 1 day
            stale_while_revalidate=5 * 60,    # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def profile(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(
            request.current_route_path(username=user.username),
        )

    projects = (
        request.db.query(Release)
                  .options(joinedload(Release.project))
                  .join(Project)
                  .distinct(Project.name)
                  .filter(Project.users.contains(user))
                  .order_by(Project.name, Release._pypi_ordering.desc())
                  .all()
    )

    return {"user": user, "projects": projects}


@view_config(
    route_name="accounts.login",
    renderer="accounts/login.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def login(request, redirect_field_name=REDIRECT_FIELD_NAME,
          _form_class=forms.LoginForm):
    # TODO: Logging in should reset request.user
    # TODO: Configure the login view as the default view for not having
    #       permission to view something.

    user_service = request.find_service(IUserService, context=None)

    redirect_to = request.POST.get(redirect_field_name,
                                   request.GET.get(redirect_field_name))

    form = _form_class(request.POST, user_service=user_service)

    if request.method == "POST" and form.validate():
        # Get the user id for the given username.
        username = form.username.data
        userid = user_service.find_userid(username)

        # If the user-originating redirection url is not safe, then redirect to
        # the index instead.
        if (not redirect_to or
                not is_safe_url(url=redirect_to, host=request.host)):
            redirect_to = "/"

        # Actually perform the login routine for our user.
        headers = _login_user(request, userid)

        # Now that we're logged in we'll want to redirect the user to either
        # where they were trying to go originally, or to the default view.
        resp = HTTPSeeOther(redirect_to, headers=dict(headers))

        # We'll use this cookie so that client side javascript can Determine
        # the actual user ID (not username, user ID). This is *not* a security
        # sensitive context and it *MUST* not be used where security matters.
        #
        # We'll also hash this value just to avoid leaking the actual User IDs
        # here, even though it really shouldn't matter.
        resp.set_cookie(
            USER_ID_INSECURE_COOKIE,
            blake2b(
                str(userid).encode("ascii"),
                person=b"warehouse.userid",
            ).hexdigest().lower(),
        )

        return resp

    return {
        "form": form,
        "redirect": {
            "field": REDIRECT_FIELD_NAME,
            "data": redirect_to,
        },
    }


@view_config(
    route_name="accounts.logout",
    renderer="accounts/logout.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def logout(request, redirect_field_name=REDIRECT_FIELD_NAME):
    # TODO: If already logged out just redirect to ?next=
    # TODO: Logging out should reset request.user

    redirect_to = request.POST.get(redirect_field_name,
                                   request.GET.get(redirect_field_name))

    if request.method == "POST":
        # A POST to the logout view tells us to logout. There's no form to
        # validate here because there's no data. We should be protected against
        # CSRF attacks still because of the CSRF framework, so users will still
        # need a post body that contains the CSRF token.
        headers = forget(request)

        # When crossing an authentication boundary we want to create a new
        # session identifier. We don't want to keep any information in the
        # session when going from authenticated to unauthenticated because
        # user's generally expect that logging out is a destructive action
        # that erases all of their private data. However, if we don't clear the
        # session then another user can use the computer after them, log in to
        # their account, and then gain access to anything sensitive stored in
        # the session for the original user.
        request.session.invalidate()

        # If the user-originating redirection url is not safe, then redirect to
        # the index instead.
        if (not redirect_to or
                not is_safe_url(url=redirect_to, host=request.host)):
            redirect_to = "/"

        # Now that we're logged out we'll want to redirect the user to either
        # where they were originally, or to the default view.
        resp = HTTPSeeOther(redirect_to, headers=dict(headers))

        # Ensure that we delete our user_id__insecure cookie, since the user is
        # no longer logged in.
        resp.delete_cookie(USER_ID_INSECURE_COOKIE)

        return resp

    return {"redirect": {"field": REDIRECT_FIELD_NAME, "data": redirect_to}}


@view_config(
    route_name="accounts.register",
    renderer="accounts/register.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def register(request, _form_class=forms.RegistrationForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther("/")

    user_service = request.find_service(IUserService, context=None)
    recaptcha_service = request.find_service(name="recaptcha")
    request.find_service(name="csp").merge(recaptcha_service.csp_policy)

    # the form contains an auto-generated field from recaptcha with
    # hyphens in it. make it play nice with wtforms.
    post_body = {
        key.replace("-", "_"): value
        for key, value in request.POST.items()
    }

    form = _form_class(
        data=post_body, user_service=user_service,
        recaptcha_service=recaptcha_service
    )

    if request.method == "POST" and form.validate():
        user = user_service.create_user(
            form.username.data, form.full_name.data, form.password.data,
            form.email.data
        )

        return HTTPSeeOther(
            request.route_path("index"),
            headers=dict(_login_user(request, user.id)))

    return {"form": form}


def _login_user(request, userid):
        # We have a session factory associated with this request, so in order
        # to protect against session fixation attacks we're going to make sure
        # that we create a new session (which for sessions with an identifier
        # will cause it to get a new session identifier).

        # We need to protect against session fixation attacks, so make sure
        # that we create a new session (which will cause it to get a new
        # session identifier).
        if (request.unauthenticated_userid is not None and
                request.unauthenticated_userid != userid):
            # There is already a userid associated with this request and it is
            # a different userid than the one we're trying to remember now. In
            # this case we want to drop the existing session completely because
            # we don't want to leak any data between authenticated userids.
            request.session.invalidate()
        else:
            # We either do not have an associated userid with this request
            # already, or the userid is the same one we're trying to remember
            # now. In either case we want to keep all of the data but we want
            # to make sure that we create a new session since we're crossing
            # a privilege boundary.
            data = dict(request.session.items())
            request.session.invalidate()
            request.session.update(data)

        # Remember the userid using the authentication policy.
        headers = remember(request, str(userid))

        # Cycle the CSRF token since we've crossed an authentication boundary
        # and we don't want to continue using the old one.
        request.session.new_csrf_token()

        # Whenever we log in the user, we want to update their user so that it
        # records when the last login was.
        user_service = request.find_service(IUserService, context=None)
        user_service.update_user(userid, last_login=datetime.datetime.utcnow())

        return headers
