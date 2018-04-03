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


def _forwarded_value(values, num_proxies):
    values = [v.strip() for v in values.split(",")]
    if len(values) >= num_proxies:
        return values[-num_proxies]


class ProxyFixer:

    def __init__(self, app, token, num_proxies=1):
        self.app = app
        self.token = token
        self.num_proxies = num_proxies

    def __call__(self, environ, start_response):
        # Determine if the request comes from a trusted proxy or not by looking
        # for a token in the request.
        request_token = environ.get("HTTP_WAREHOUSE_TOKEN")
        if (request_token is not None and
                hmac.compare_digest(self.token, request_token)):
            # Compute our values from the environment.
            proto = environ.get("HTTP_WAREHOUSE_PROTO", "")
            remote_addr = environ.get("HTTP_WAREHOUSE_IP", "")
            host = environ.get("HTTP_WAREHOUSE_HOST", "")
        # If we're not getting headers from a trusted third party via the
        # specialized Warehouse-* headers, then we'll fall back to looking at
        # X-Fowarded-* headers, assuming that whatever we have in front of us
        # will strip invalid ones.
        else:
            proto = environ.get("HTTP_X_FORWARDED_PROTO", "")
            remote_addr = _forwarded_value(
                environ.get("HTTP_X_FORWARDED_FOR", ""),
                self.num_proxies,
            )
            host = environ.get("HTTP_X_FORWARDED_HOST", "")

        # Put the new header values into our environment.
        if remote_addr:
            environ["REMOTE_ADDR"] = remote_addr
        if host:
            environ["HTTP_HOST"] = host
        if proto:
            environ["wsgi.url_scheme"] = proto

        # Remove any of the forwarded or warehouse headers from the environment
        for header in {
                "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_FOR",
                "HTTP_X_FORWARDED_HOST", "HTTP_X_FORWARDED_PORT",
                "HTTP_WAREHOUSE_TOKEN", "HTTP_WAREHOUSE_PROTO",
                "HTTP_WAREHOUSE_IP", "HTTP_WAREHOUSE_HOST"}:
            if header in environ:
                del environ[header]

        # Dispatch to the real underlying application.
        return self.app(environ, start_response)


class VhmRootRemover:

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Delete the X-Vhm-Root header if it exists.
        if "HTTP_X_VHM_ROOT" in environ:
            del environ["HTTP_X_VHM_ROOT"]

        return self.app(environ, start_response)


class HostRewrite:

    # TODO: This entire class should not be required.

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # If the host header matches upload.pypi.io, then we want to rewrite it
        # so that it is instead upload.pypi.org.
        if environ.get("HTTP_HOST", "").lower() == "upload.pypi.io":
            environ["HTTP_HOST"] = "upload.pypi.org"

        return self.app(environ, start_response)
