# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import collections
import functools
import mimetypes
import re
import string

from werkzeug.urls import iri_to_uri
from werkzeug.utils import escape

from warehouse import helpers
from warehouse.http import Response


class AttributeDict(dict):

    def __getattr__(self, name):
        if not name in self:
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__,
                name,
            ))

        return self[name]


def merge_dict(base, additional):
    if base is None:
        return additional

    if additional is None:
        return base

    if not (isinstance(base, collections.Mapping)
            and isinstance(additional, collections.Mapping)):
        return additional

    merged = base
    for key, value in additional.items():
        if isinstance(value, collections.Mapping):
            merged[key] = merge_dict(merged.get(key), value)
        else:
            merged[key] = value

    return merged


def convert_to_attr_dict(dictionary):
    output = {}
    for key, value in dictionary.items():
        if isinstance(value, collections.Mapping):
            output[key] = convert_to_attr_dict(value)
        else:
            output[key] = value
    return AttributeDict(output)


def render_response(app, request, template, **variables):
    template = app.templates.get_template(template)

    context = {
        "config": app.config,
        "url_for": functools.partial(helpers.url_for, request),
    }
    context.update(variables)

    return Response(template.render(**context), mimetype="text/html")


def cache(key):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(app, request, *args, **kwargs):
            resp = fn(app, request, *args, **kwargs)

            if 200 <= resp.status_code < 400:
                # Add in our standard Cache-Control headers
                if (app.config.cache.browser
                        and app.config.cache.browser.get(key) is not None):
                    resp.cache_control.public = True
                    resp.cache_control.max_age = app.config.cache.browser[key]

                # Add in additional headers if we're using varnish
                if (app.config.cache.varnish
                        and app.config.cache.varnish.get(key) is not None):
                    resp.surrogate_control.public = True
                    resp.surrogate_control.max_age = \
                        app.config.cache.varnish[key]

            return resp
        return wrapper
    return deco


def get_wsgi_application(environ, app_class):
    if "WAREHOUSE_CONF" in environ:
        configs = [environ["WAREHOUSE_CONF"]]
    else:
        configs = []

    return app_class.from_yaml(*configs)


def get_mimetype(filename):
    # Figure out our mimetype
    mimetype = mimetypes.guess_type(filename)[0]
    if not mimetype:
        mimetype = "application/octet-stream"
    return mimetype


def redirect(location, code=302):
    """Return a response object (a WSGI application) that, if called,
    redirects the client to the target location.  Supported codes are 301,
    302, 303, 305, and 307.  300 is not supported because it's not a real
    redirect and 304 because it's the answer for a request with a request
    with defined If-Modified-Since headers.

    .. versionadded:: 0.6
       The location can now be a unicode string that is encoded using
       the :func:`iri_to_uri` function.

    :param location: the location the response should redirect to.
    :param code: the redirect status code. defaults to 302.
    """
    display_location = escape(location)
    if isinstance(location, str):
        location = iri_to_uri(location)
    response = Response(
        '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
        '<title>Redirecting...</title>\n'
        '<h1>Redirecting...</h1>\n'
        '<p>You should be redirected automatically to target URL: '
        '<a href="%s">%s</a>.  If not click the link.' %
        (escape(location), display_location), code, mimetype="text/html")
    response.headers["Location"] = location
    return response


def normalize(value):
    return re.sub("_", "-", value, re.I).lower()


class FastlyFormatter(string.Formatter):

    def convert_field(self, value, conversion):
        if conversion == "n":
            return normalize(value)
        return super(FastlyFormatter, self).convert_field(value, conversion)


def fastly(*keys):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(app, request, *args, **kwargs):
            # Get the response from the view
            resp = fn(app, request, *args, **kwargs)

            # Resolve our surrogate keys
            ctx = {"app": app, "request": request}
            ctx.update(kwargs)
            surrogate_keys = [
                FastlyFormatter().format(key, **ctx)
                for key in keys
            ]

            # Set our Fastly Surrogate-Key header
            resp.headers["Surrogate-Key"] = " ".join(surrogate_keys)

            # Return the modified response
            return resp
        return wrapper
    return decorator
