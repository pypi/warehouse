# SPDX-License-Identifier: Apache-2.0

import functools

from warehouse.cache.origin.interfaces import IOriginCache


def html_cache_deriver(view, info):
    renderer = info.options.get("renderer")
    if renderer and renderer.name.endswith(".html"):

        def wrapper_view(context, request):
            try:
                cacher = request.find_service(IOriginCache)
            except LookupError:
                pass
            else:
                request.add_response_callback(
                    functools.partial(cacher.cache, ["all-html", renderer.name])
                )

            return view(context, request)

        return wrapper_view
    return view
