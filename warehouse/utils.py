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

import six

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
    for key, value in six.iteritems(additional):
        if isinstance(value, collections.Mapping):
            merged[key] = merge_dict(merged.get(key), value)
        else:
            merged[key] = value

    return merged


def convert_to_attr_dict(dictionary):
    output = {}
    for key, value in six.iteritems(dictionary):
        if isinstance(value, collections.Mapping):
            output[key] = convert_to_attr_dict(value)
        else:
            output[key] = value
    return AttributeDict(output)


def render_response(app, request, template, **variables):
    template = app.templates.get_template(template)

    context = {
        "url_for": functools.partial(helpers.url_for, request),
    }
    context.update(variables)

    return Response(template.render(**context), mimetype="text/html")


def cache(key):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(app, request, *args, **kwargs):
            resp = fn(app, request, *args, **kwargs)

            # Add in our standard Cache-Control headers
            if (app.config.cache.browser
                    and app.config.cache.browser.get(key) is not None):
                resp.cache_control.public = True
                resp.cache_control.max_age = app.config.cache.browser[key]

            # Add in additional headers if we're using varnish
            if (app.config.cache.varnish
                    and app.config.cache.varnish.get(key) is not None):
                resp.surrogate_control.public = True
                resp.surrogate_control.max_age = app.config.cache.varnish[key]

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
