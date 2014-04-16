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


class TemplateResponse(Response):
    """
    TemplateResponse is small subclass of Response which will lazily render
    a template when the response attribute is accessed.

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

    def __init__(self, template, context, *args, default_context=None,
                 **kwargs):
        super(TemplateResponse, self).__init__(*args, **kwargs)

        self.template = template
        self.context = context
        self.default_context = default_context if default_context else {}

    @property
    def response(self):
        """
        The actual content of the response. The first time this is accessed
        we'll render the template and set are attributes to None so that
        it cannot be mistakenly attempted to modify after it has already been
        rendered.
        """
        if not hasattr(self, "_response"):
            ctx = self.default_context.copy()
            ctx.update(self.context)

            self._response = self.template.render(**ctx)

            self.template = None
            self.default_context = None
            self.context = None
        return self._response

    @response.setter
    def response(self, value):
        """
        If something sets a positive value to the response, go ahead and allow
        that to replace our lazily evaluated response.
        """
        if value:
            self._response = value


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
        template,
        context,
        default_context=default_context,
        mimetype="text/html",
    )
