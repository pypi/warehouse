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
import functools

import msgpack
import msgpack.exceptions

from pyramid import viewderivers
from pyramid.renderers import render_to_response

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.interfaces import IUserService
from warehouse.manage.forms import ReAuthenticateForm  # TODO: move to accounts yea
from warehouse.utils import crypto
from warehouse.utils.http import is_safe_url
from warehouse.utils.msgpack import object_encode


class ReAuthenticationView(object):
    def __init__(self, request):
        self.request = request

    def __call__(self):
        user_service = self.request.find_service(IUserService, context=None)

        form = ReAuthenticateForm(
            self.request.POST, request=self.request, user_service=user_service,
        )

        return render_to_response(
            "re-auth.html",
            {"form": form, "user": self.request.user},
            request=self.request,
        )


# test to make sure that they're being called with the gated action


def reauth_view(view, info):
    if info.options.get("require_reauth"):

        @functools.wraps(view)
        def wrapped(context, request):
            print(f"REQUEST REDIRECT: {request.matched_route.name}")
            re_auth_view = ReAuthenticationView(request)

            if request.session.needs_reauthentication(request):
                return re_auth_view()

            return view(context, request)

        return wrapped

    return view


reauth_view.options = {"require_reauth"}


def includeme(config):
    config.add_view_deriver(
        reauth_view, over="rendered_view", under=viewderivers.INGRESS
    )
