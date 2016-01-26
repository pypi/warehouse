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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPSeeOther
from pyramid.security import remember, forget
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.forms import LoginForm
from warehouse.accounts.interfaces import IUserService
from warehouse.cache.origin import origin_cache
from warehouse.csrf import csrf_protect
from warehouse.packaging.models import Project, Release
from warehouse.sessions import uses_session
from warehouse.utils.http import is_safe_url


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
                  .order_by(Project.name)
                  .all()
    )

    return {"user": user, "projects": projects}


@view_config(
    route_name="accounts.login",
    renderer="accounts/login.html",
    decorator=[csrf_protect("accounts.login"), uses_session],
)
def login(request, redirect_field_name=REDIRECT_FIELD_NAME,
          _form_class=LoginForm):
    # TODO: Logging in should reset request.user
    # TODO: Configure the login view as the default view for not having
    #       permission to view something.

    login_service = request.find_service(IUserService, context=None)

    redirect_to = request.POST.get(redirect_field_name,
                                   request.GET.get(redirect_field_name))

    form = _form_class(request.POST, login_service=login_service)

    if request.method == "POST" and form.validate():
        # Get the user id for the given username.
        username = form.username.data
        userid = login_service.find_userid(username)

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
        headers = remember(request, userid)

        # Cycle the CSRF token since we've crossed an authentication boundary
        # and we don't want to continue using the old one.
        request.session.new_csrf_token()

        # If the user-originating redirection url is not safe, then redirect to
        # the index instead.
        if (not redirect_to or
                not is_safe_url(url=redirect_to, host=request.host)):
            redirect_to = "/"

        # Now that we're logged in we'll want to redirect the user to either
        # where they were trying to go originally, or to the default view.
        return HTTPSeeOther(redirect_to, headers=dict(headers))

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
    decorator=[csrf_protect("accounts.logout"), uses_session],
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
        return HTTPSeeOther(redirect_to, headers=dict(headers))

    return {"redirect": {"field": REDIRECT_FIELD_NAME, "data": redirect_to}}


@view_config(
    route_name="accounts.mark-insecure",
    renderer="accounts/mark_insecure.html",
    decorator=[csrf_protect("accounts.mark-insecure"), uses_session],
)
def mark_insecure(request):

    # Todo: write a real view here

    # if the user is not logged in, return a redirect to the login page with
    # the REDIRECT_URL pointing as parameter that points back to this view.
    if request.authenticated_userid is None:
        pass

    projects = [
        {
            "name": "Django",
            "releases": [
                '1.9rc1', '1.9b1', '1.9a1', '1.8.6', '1.8.5', '1.8.4',
                '1.8.3', '1.8.2', '1.8.1', '1.8', '1.8c1', '1.8b2',
                '1.8b1', '1.8a1', '1.7.10', '1.7.9', '1.7.8', '1.7.7',
                '1.7.6', '1.7.5', '1.7.4', '1.7.3', '1.7.2', '1.7.1',
                '1.7', '1.6.11', '1.6.10', '1.6.9', '1.6.8', '1.6.7',
                '1.6.6', '1.6.5', '1.6.4', '1.6.3', '1.6.2', '1.6.1',
                '1.6', '1.5.12', '1.5.11', '1.5.10', '1.5.9', '1.5.8',
                '1.5.7', '1.5.6', '1.5.5', '1.5.4', '1.5.3', '1.5.2',
                '1.5.1', '1.5', '1.4.22', '1.4.21', '1.4.20', '1.4.19',
                '1.4.18', '1.4.17', '1.4.16',  '1.4.15', '1.4.14',
                '1.4.13', '1.4.12', '1.4.11', '1.4.10', '1.4.9', '1.4.8',
                '1.4.7', '1.4.6', '1.4.5', '1.4.4', '1.4.3', '1.4.2',
                '1.4.1', '1.4'
            ]
        },
        {"name": "Flask", "releases": ["0.1.0"]}
    ]
    return {
        "projects": projects,
    }
