# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterable
from typing import Any

import sentry_sdk

from pyramid.httpexceptions import HTTPBadRequest, HTTPException
from pyramid.view import exception_view_config


# We don't subclass from a HTTP Exception here, because pyramid will automatically
# turn those into a response for us, and we don't want that to happen "silently"
# for these exceptions.
#
# In other words, a ForkliftError is only intended to be raised from within
# forklift, and forklift should always have an exception view applied that does the
# translation to what Pyramid expects, so these should never reach Pyramid itself,
# and if they do, then something has gone wrong and we should be alerted to that
# fact.
#
# All of our ForkliftErrors have certain values that are set at the class
# level (like a message, tags to emit in the metrics, etc) and accept arbitrary
# keyword arguments which will be formatted into those values at runtime.
#
# This means we can have a message (or a tag, or whatever) that says something
# like `message = "this is an error with {foo}` and you can pass in foo as a
# keyword argument to the ForkliftError.
class ForkliftError(Exception):
    message: str
    tags: set[str]
    values: dict[str, Any]

    _message_template: str
    _tag_templates: set[str]
    _http_exception_type: HTTPException
    _help_anchor: str | None
    _help_url: str | None
    _user_docs_path: str | None
    _user_docs_anchor: str | None

    # We use an __init_subclass__ hook to make it impossible for a subclass to
    # forget to specify either a message or a set of tags, which they could do
    # if we just used "normal" class variables.
    #
    # This also means that our class variables that we use to smuggle these values
    # into the __init__ and as_http_exception methods don't need nice human readable
    # names, because they're just part of the internal details of this class.
    def __init_subclass__(
        cls,
        *,
        message: str,
        tags: Iterable[str],
        error_type=HTTPBadRequest,
        help_anchor=None,
        user_docs_path=None,
        user_docs_anchor=None,
        help_url=None,
        **kwargs,
    ):
        # This is the template that we'll use to render the base "message" of
        # the error, which will get treated as if the user did Foo(message), but
        # with the string template expanded.
        cls._message_template = message

        # This is the set of tags that we'll use when emitting metrics, again
        # this will end up expanded with the kwargs.
        cls._tag_templates = set(tags)

        # This is the HttpException that this exception will actually raise when
        # it gets translated from a ForkliftException to a HttpException.
        cls._http_exception_type = error_type

        # If there is a help anchor (which is pointing to the standad help url)
        # associated with this, then when we translate this error we'll also
        # automatically include a link to the help url in the message as well.
        cls._help_anchor = help_anchor

        # We also have user docs, and we point some of our errors to that.
        cls._user_docs_path = user_docs_path
        cls._user_docs_anchor = user_docs_anchor

        # If there is a help url, then we assume it is an already resolved url
        # that we can include in the response to direct the user towards help.
        cls._help_url = help_url

        # Let the normal behavior finish initializing the subclass.
        super().__init_subclass__(**kwargs)

    def __init__(self, *args, **kwargs):
        # We're going to generate a "real" message by using the kwards to format
        # against the message template stored on the class, and then pass that
        # into the parent class as if it was called like Foo("result of template").
        self.message = self._message_template.format(**kwargs)

        # Like message, our tags are also formatted by the kwargs, but we're just
        # going to store them ourselves because our parent class doesn't have any
        # concept of tags that we'd want to mimic.
        self.tags = {t.format(**kwargs) for t in self._tag_templates}

        # Store our values that were passed in here so they're easy to introspect
        # later.
        self.values = kwargs

        # We do this last, so that all of our pre-formatting has already taken
        # into effect before this happens.
        super().__init__(self.message, *args)

    def as_http_exception(self, request):
        # TODO: Is this something we still need to worry about?
        if not self.message:
            sentry_sdk.capture_message(
                "Attempting to _exc_with_message without a message"
            )

        # Append the standard "see X for more info" message to our message if there
        # a help url associated with this error.
        # TODO: Handle _help_url, and multiples and _user_docs_anchor, _user_docs_path
        message = self.message
        if self._help_anchor is not None:
            message += " See {help_url} for more information.".format(
                help_url=request.help_url(_anchor=self._help_anchor)
            )

        # Actually construct the "real" http error, using our now finalized message.
        return _exc_with_message(self._http_exception_type, message)


# This is kept as a stand alone function to support the handful of non-upload endpoints
# in Forklift, at least until we have a better pattern for handling metrics that would
# let us re-use the translate_error machinery without emitting spurious metrics.
def _exc_with_message(exc, message, **kwargs):
    # TODO: Is this something we still need to worry about?
    if not message:
        sentry_sdk.capture_message("Attempting to _exc_with_message without a message")

    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client, so we'll construct a normal http exception,
    # but then set the "status" to our error message as well.
    resp = exc(detail=message, **kwargs)
    # We need to guard against characters outside of iso-8859-1 per RFC.
    # Specifically here, where user-supplied text may appear in the message,
    # which our WSGI server may not appropriately handle (indeed gunicorn does not).
    status_message = message.encode("iso-8859-1", "replace").decode("iso-8859-1")
    resp.status = f"{resp.status_code} {status_message}"
    return resp


@exception_view_config(ForkliftError, route_name="forklift.legacy.file_upload")
def forklift_error(exc, request):
    request.metrics.increment("warehouse.upload.failed", tags=exc.tags)
    return exc.as_http_exception(request)
