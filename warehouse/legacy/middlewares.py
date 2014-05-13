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

from warehouse.http import Request


class LegacyRewriteMiddleware:
    """
    This middleware handles rewriting the legacy URLs and requests in order to
    make it possible to dispatch them to different functions using the standard
    Werkzeug dispatcher.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        request = Request(environ, populate_request=False, shallow=True)

        # Our Legacy URLs are *always* under /pypi
        if request.path[1:].split("/")[0] == "pypi":
            # if the MIME type of the request is XML then we rewrite to our
            # XMLRPC URL
            if request.headers.get('Content-Type') == 'text/xml':
                environ["PATH_INFO"] = "/_legacy/xmlrpc/"

        return self.app(environ, start_response)
