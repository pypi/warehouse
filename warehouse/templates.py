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

    def __init__(self, template, context, *args, default_context=None,
                 **kwargs):
        super(TemplateResponse, self).__init__(*args, **kwargs)

        self.template = template
        self.context = context
        self.default_context = default_context if default_context else {}

    @property
    def response(self):
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
        if value:
            self._response = value


def render_response(app, request, template, **context):
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
