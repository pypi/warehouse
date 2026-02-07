# SPDX-License-Identifier: Apache-2.0

import orjson

from warehouse.legacy.api.xmlrpc.cache import interfaces


def cached_return_view(view, info):
    if info.options.get("xmlrpc_cache"):
        tag = info.options.get("xmlrpc_cache_tag")
        expires = info.options.get("xmlrpc_cache_expires", 86400)
        arg_index = info.options.get("xmlrpc_cache_arg_index")
        slice_obj = info.options.get("xmlrpc_cache_slice_obj", slice(None, None))
        tag_processor = info.options.get(
            "xmlrpc_cache_tag_processor", lambda x: x.lower()
        )

        def wrapper_view(context, request):
            try:
                service = request.find_service(interfaces.IXMLRPCCache)
            except LookupError:
                return view(context, request)
            try:
                key = orjson.dumps(request.rpc_args[slice_obj])
                _tag = tag
                if arg_index is not None:
                    _tag = tag % (tag_processor(str(request.rpc_args[arg_index])))
                return service.fetch(view, (context, request), {}, key, _tag, expires)
            except (interfaces.CacheError, IndexError):
                return view(context, request)

        return wrapper_view
    return view


cached_return_view.options = [  # type: ignore
    "xmlrpc_cache",
    "xmlrpc_cache_tag",
    "xmlrpc_cache_expires",
    "xmlrpc_cache_arg_index",
    "xmlrpc_cache_slice_obj",
    "xmlrpc_cache_tag_processor",
]
