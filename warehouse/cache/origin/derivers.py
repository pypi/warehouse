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

from warehouse.cache.origin.interfaces import IOriginCache


def html_cache_deriver(view, info):
    renderer = info.options.get('renderer')
    if renderer and renderer.name.endswith('.html'):
        def wrapper_view(context, request):
            try:
                cacher = request.find_service(IOriginCache)
            except ValueError:
                pass
            else:
                request.add_response_callback(
                    functools.partial(
                        cacher.cache,
                        sorted(['all-html', renderer.name]),
                        seconds=1 * 24 * 60 * 60,                 # 1 day
                        stale_while_revalidate=5 * 60,    # 5 minutes
                        stale_if_error=1 * 24 * 60 * 60,  # 1 day
                    )
                )
            return view(context, request)
        return wrapper_view
    return view
