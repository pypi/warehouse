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
import hmac


class XForwardedTokenMiddleware:

    header = "HTTP_X_WAREHOUSE_ACCESS_TOKEN"

    def __init__(self, app, token):
        self.app = app
        self.token = token

    def __call__(self, environ, start_response):
        # Filter out X-Forwarded-* headers from the request if the secret token
        # does not exist or does not match.
        if not hmac.compare_digest(environ.pop(self.header, ""), self.token):
            for key in set(environ.keys()):
                if key.startswith("HTTP_X_FORWARDED_"):
                    del environ[key]

        return self.app(environ, start_response)
