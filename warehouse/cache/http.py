# SPDX-License-Identifier: Apache-2.0

import collections.abc
import functools

BUFFER_MAX = 1 * 1024 * 1024  # We'll buffer up to 1MB


def add_vary_callback(*varies):
    def inner(request, response):
        vary = set(response.vary if response.vary is not None else [])
        vary |= set(varies)
        response.vary = vary

    return inner


def add_vary(*varies):
    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            request.add_response_callback(add_vary_callback(*varies))
            return view(context, request)

        return wrapped

    return inner


def cache_control(
    seconds, *, public=True, stale_while_revalidate=None, stale_if_error=None
):
    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            response = view(context, request)

            if not request.registry.settings.get("pyramid.prevent_http_cache", False):
                if seconds:
                    if public:
                        response.cache_control.public = True
                    else:
                        response.cache_control.private = True

                    response.cache_control.stale_while_revalidate = (
                        stale_while_revalidate
                    )
                    response.cache_control.stale_if_error = stale_if_error
                    response.cache_control.max_age = seconds
                else:
                    response.cache_control.no_cache = True
                    response.cache_control.no_store = True
                    response.cache_control.must_revalidate = True

            return response

        return wrapped

    return inner


def conditional_http_tween_factory(handler, registry):
    def conditional_http_tween(request):
        response = handler(request)

        # If the Last-Modified header has been set, we want to enable the
        # conditional response processing.
        if response.last_modified is not None:
            response.conditional_response = True

        streaming = not isinstance(response.app_iter, collections.abc.Sequence)

        # We want to only enable the conditional machinery if either we
        # were given an explicit ETag header by the view or we have a
        # buffered response and can generate the ETag header ourself.
        if response.etag is not None:
            response.conditional_response = True
        # We can only reasonably implement automatic ETags on 200 responses
        # to GET or HEAD requests. The subtles of doing it in other cases
        # are too hard to get right.
        elif request.method in {"GET", "HEAD"} and response.status_code == 200:
            # If we have a streaming response, but it's small enough, we'll
            # just go ahead and buffer it in memory so that we can generate a
            # ETag for it.
            if (
                streaming
                and response.content_length is not None
                and response.content_length <= BUFFER_MAX
            ):
                response.body
                streaming = False

            # Anything that has survived as a streaming response at this point
            # and doesn't have an ETag header already, we'll go ahead and give
            # it one.
            if not streaming:
                response.conditional_response = True
                response.md5_etag()

        return response

    return conditional_http_tween


def includeme(config):
    config.add_tween("warehouse.cache.http.conditional_http_tween_factory")
