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

from pyramid.session import check_csrf_origin, check_csrf_token
from pyramid.viewderivers import INGRESS, SAFE_REQUEST_METHODS, secured_view

from warehouse.utils.http import require_safe


def csrf_view(view, info):
    require_csrf = info.options.get("require_csrf")

    # If this view doesn't have any CSRF checking configured, then we want to
    # wrap the view so that it will only accept "safe" methods and will flat
    # out, unconditionally reject any other methods. We do this instead of
    # just checking for CSRF tokens because CSRF tokens make the page content
    # conditional on what cookies you have, and thus we'd need to have
    # Vary: Cookie on every HTTP request.
    if require_csrf is None:
        return require_safe(view)
    # If the user has explicitly opted into CSRF checking by setting
    # require_csrf=True then we'll go ahead and validate against CSRF here.
    elif require_csrf:
        @functools.wraps(view)
        def wrapped(context, request):
            # Assume that anything not defined as 'safe' by RFC2616 needs
            # protection
            if request.method not in SAFE_REQUEST_METHODS:
                check_csrf_origin(request, raises=True)
                check_csrf_token(request, raises=True)
            return view(context, request)

        return wrapped
    # Finally, if we've explicitly opted out of CSRF checking by setting
    # require_csrf=False then we'll go ahead and just allow the view to pass
    # through unmodified.
    else:
        return view

csrf_view.options = {"require_csrf"}


def includeme(config):
    # We want to shuffle things around so that the csrf_view comes over the
    # secured_view because we do not want to access the ambient authority
    # provided by the session cookie without first checking to ensure that this
    # is not a cross-site request.
    config.add_view_deriver(csrf_view, under=INGRESS, over="secured_view")
    config.add_view_deriver(secured_view, under="csrf_view")
