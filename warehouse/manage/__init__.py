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

from pyramid.renderers import render_to_response

from warehouse.accounts.forms import ReAuthenticateForm
from warehouse.accounts.interfaces import IUserService
from warehouse.rate_limiting import IRateLimiter, RateLimit

DEFAULT_TIME_TO_REAUTH = 30 * 60  # 30 minutes


def reauth_view(view, info):
    require_reauth = info.options.get("require_reauth")

    if require_reauth:
        # If it's True, we use the default, otherwise use the value provided
        time_to_reauth = (
            DEFAULT_TIME_TO_REAUTH if require_reauth is True else require_reauth
        )

        @functools.wraps(view)
        def wrapped(context, request):
            if request.session.needs_reauthentication(time_to_reauth):
                user_service = request.find_service(IUserService, context=None)

                form = ReAuthenticateForm(
                    request.POST,
                    request=request,
                    username=request.user.username,
                    next_route=request.matched_route.name,
                    next_route_matchdict=json.dumps(request.matchdict),
                    next_route_query=json.dumps(request.GET.mixed()),
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


reauth_view.options = {"require_reauth"}  # type: ignore


def includeme(config):
    config.add_view_deriver(reauth_view, over="rendered_view", under="decorated_view")

    user_oidc_registration_ratelimit_string = config.registry.settings.get(
        "warehouse.manage.oidc.user_registration_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(user_oidc_registration_ratelimit_string),
        IRateLimiter,
        name="user_oidc.publisher.register",
    )

    ip_oidc_registration_ratelimit_string = config.registry.settings.get(
        "warehouse.manage.oidc.ip_registration_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(ip_oidc_registration_ratelimit_string),
        IRateLimiter,
        name="ip_oidc.publisher.register",
    )
