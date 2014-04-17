# Copyright 2014 Donald Stufft
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

import functools

from warehouse import helpers
from warehouse.http import Response


class TemplateRenderer:
    """
    TemplateRenderer is small iterator which will lazily render
    a template when consumed.

    This allows inspecting or even modifying the context of the template, or
    even the template itself, at anytime prior to the template finally being
    rendered. Specifically it allows tests to easily test that a view has
    rendered a particular template with a particular context, but it also
    additionally allows decorators to modify the response without having to
    resort to parsing HTML.

    It also allows you to conceptually separate a ``default_context`` from the
    actual ``context``. This distinction is useful because ``render_response``
    always adds some default context to the template but that isn't useful for
    testing or modification of what the view itself has done.
    """

    def __init__(self, template, context, default_context=None):
        if default_context is None:
            default_context = {}

        self.template = template
        self.context = context
        self.default_context = default_context
        self.rendered = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.rendered:
            raise StopIteration

        self.rendered = True

        ctx = self.default_context.copy()
        ctx.update(self.context)

        return self.template.render(**ctx)


class TemplateResponse(Response):
    """
    TemplateResponse is a Response subclass which ensures that a
    TemplateRenderer instance does not cause the request to be streaming but
    instead causes it to be a typical request.
    """

    def __repr__(self):
        self._ensure_sequence()
        return super(TemplateResponse, self).__repr__()

    def get_wsgi_headers(self, environ):
        headers = super(TemplateResponse, self).get_wsgi_headers(environ)
        headers["Content-Length"] = self.calculate_content_length()

        return headers

    @property
    def is_streamed(self):
        return False


def render_response(app, request, template, **context):
    """
    A simple helper that takes an app, request, template, and some context and
    constructs a TemplateResponse that will lazily render the template with
    the given context when the Response is evaluated.
    """
    template = app.templates.get_template(template)

    default_context = {
        "config": app.config,
        "csrf_token": functools.partial(helpers.csrf_token, request),
        "gravatar_url": helpers.gravatar_url,
        "static_url": functools.partial(helpers.static_url, app),
        "url_for": functools.partial(helpers.url_for, request),
    }

    return TemplateResponse(
        TemplateRenderer(template, context, default_context=default_context),
        mimetype="text/html",
    )
