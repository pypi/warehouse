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
import redis

from pyramid import viewderivers
from pyramid.renderers import render_to_response

from warehouse.accounts.interfaces import IUserService
from warehouse.manage.forms import ReAuthenticateForm  # TODO: move to accounts yea
from warehouse.utils import crypto
from warehouse.utils.http import is_safe_url
from warehouse.utils.msgpack import object_encode

RE_AUTHENTICATION_KEY = "session_reauth__time"


class ReAuthenticationView(object):
    cookie_name = "session_id"
    max_age = 60 * 60

    def __init__(self, request):
        self.request = request
        self.redis = redis.StrictRedis.from_url(
            request.registry.settings["sessions.url"]
        )
        self.signer = crypto.Signer(
            request.registry.settings["sessions.secret"], salt="session"
        )

        self.response_call = lambda: None

    def check_session_cookie(self):
        def response_call():
            user_service = self.request.find_service(IUserService, context=None)

            form = ReAuthenticateForm(
                self.request.POST, request=self.request, user_service=user_service,
            )  # TODO: fill in next parameter somewhere here yeah?

            return render_to_response(
                "re-auth.html",
                {"form": form, "user": self.request.user},
                request=self.request,
            )

        self.response_call = response_call

        return self._is_valid_ttl(self.request.session._sid)

    def _is_valid_ttl(self, session_id):
        try:
            auth_time = float(
                self.signer.unsign(self.request.cookies.get(RE_AUTHENTICATION_KEY))
            )
            current_time = datetime.datetime.now().timestamp()
            return current_time - auth_time < self.max_age
        except (crypto.BadSignature, ValueError):
            return False

    def __call__(self):
        return self.response_call()


# test to make sure that they're being called with the gated action


def reauth_view(view, info):
    if info.options.get("require_reauth"):

        @functools.wraps(view)
        def wrapped(context, request):
            re_auth_view = ReAuthenticationView(request)

            if re_auth_view.check_session_cookie():
                return view(context, request)

            return re_auth_view()

        return wrapped

    return view


reauth_view.options = {"require_reauth"}


def includeme(config):
    config.add_view_deriver(
        reauth_view, over="rendered_view", under=viewderivers.INGRESS
    )
