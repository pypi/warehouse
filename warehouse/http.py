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

from werkzeug.datastructures import ResponseCacheControl
from werkzeug.http import parse_cache_control_header
from werkzeug.wrappers import (
    BaseRequest, AcceptMixin, ETagRequestMixin, UserAgentMixin,
    AuthorizationMixin, CommonRequestDescriptorsMixin,
    BaseResponse, ETagResponseMixin, ResponseStreamMixin,
    CommonResponseDescriptorsMixin, WWWAuthenticateMixin,
)


class Request(BaseRequest, AcceptMixin, ETagRequestMixin,
              UserAgentMixin, AuthorizationMixin,
              CommonRequestDescriptorsMixin):
    """
    Full featured request object implementing the following mixins:

    - :class:`AcceptMixin` for accept header parsing
    - :class:`ETagRequestMixin` for etag and cache control handling
    - :class:`UserAgentMixin` for user agent introspection
    - :class:`AuthorizationMixin` for http auth handling
    - :class:`CommonRequestDescriptorsMixin` for common headers
    """


class Response(BaseResponse, ETagResponseMixin, ResponseStreamMixin,
               CommonResponseDescriptorsMixin,
               WWWAuthenticateMixin):
    """
    Full featured response object implementing the following mixins:

    - :class:`ETagResponseMixin` for etag and cache control handling
    - :class:`ResponseStreamMixin` to add support for the `stream` property
    - :class:`CommonResponseDescriptorsMixin` for various HTTP descriptors
    - :class:`WWWAuthenticateMixin` for HTTP authentication support
    """

    @property
    def surrogate_control(self):
        """
        The Cache-Control general-header field is used to specify
        directives that MUST be obeyed by all caching mechanisms along the
        request/response chain.
        """
        def on_update(surrogate_control):
            if not surrogate_control and "surrogate-control" in self.headers:
                del self.headers["surrogate-control"]
            elif surrogate_control:
                self.headers["Surrogate-Control"] = \
                    surrogate_control.to_header()
        return parse_cache_control_header(
            self.headers.get("cache-control"),
            on_update,
            ResponseCacheControl,
        )
