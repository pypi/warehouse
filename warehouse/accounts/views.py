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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.security import remember
from pyramid.view import view_config

from warehouse.accounts.forms import LoginForm
from warehouse.accounts.models import User
from warehouse.sessions import csrf_protect, uses_session


@view_config(route_name="accounts.profile", renderer="accounts/profile.html")
def profile(request, username):
    user = request.db.query(User).filter(User.username == username).first()

    if user is None:
        raise HTTPNotFound("Could not find user {}".format(username))

    if user.username != username:
        return HTTPMovedPermanently(
            request.current_route_url(username=user.username),
        )

    return {"user": user}


@view_config(route_name="accounts.login", renderer="accounts/login.html")
@csrf_protect("accounts.login")
@uses_session
def login(request):
    # TODO: Implement ?next= Support.
    # TODO: If already logged in just redirect to ?next=
    # TODO: Logging in/out should reset request.user

    form = LoginForm(
        request.POST,
        db=request.db,
        password_hasher=request.password_hasher,
    )

    if request.method == "POST" and form.validate():
        # Remember the userid using the authentication policy.
        headers = remember(request, form.user.id)
        request.response.headerlist.extend(headers)

    return {"form": form}
