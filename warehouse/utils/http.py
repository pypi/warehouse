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


def _add_vary_callback(*varies):
    def inner(request, response):
        vary = set(response.vary if response.vary is not None else [])
        vary |= set(varies)
        response.vary = vary
    return inner


def add_vary(*varies):
    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            request.add_response_callback(_add_vary_callback(*varies))
            return view(context, request)
        return wrapped
    return inner


def cache_control(seconds, public=True):
    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            response = view(context, request)

            if not request.registry.settings.get("prevent_http_cache", False):
                if seconds:
                    if public:
                        response.cache_control.public = True
                    else:
                        response.cache_control.private = True

                    response.cache_control.max_age = seconds
                else:
                    response.cache_control.no_cache = True
                    response.cache_control.no_store = True
                    response.cache_control.must_revalidate = True

            return response
        return wrapped
    return inner


def surrogate_control(seconds):
    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            response = view(context, request)

            if not request.registry.settings.get("prevent_http_cache", False):
                response.headers["Surrogate-Control"] = \
                    "max-age={}".format(seconds)

            return response
        return wrapped
    return inner
