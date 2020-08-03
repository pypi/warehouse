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

import functools
import json

from pyramid import viewderivers
from pyramid.renderers import render_to_response

from warehouse.accounts.forms import ReAuthenticateForm
from warehouse.accounts.interfaces import IUserService


def reauth_view(view, info):
    if info.options.get("require_reauth"):

        @functools.wraps(view)
        def wrapped(context, request):
            if request.session.needs_reauthentication():
                user_service = request.find_service(IUserService, context=None)

                form = ReAuthenticateForm(
                    request.POST,
                    request=request,
                    username=request.user.username,
                    next_route=request.matched_route.name,
                    next_route_matchdict=json.dumps(request.matchdict),
                    user_service=user_service,
                )

                return render_to_response(
                    "re-auth.html",
                    {"form": form, "user": request.user},
                    request=request,
                )

            return view(context, request)

        return wrapped

    return view


reauth_view.options = {"require_reauth"}


def includeme(config):
    config.add_view_deriver(
        reauth_view, over="rendered_view", under=viewderivers.INGRESS
    )
