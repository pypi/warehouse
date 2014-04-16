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

from flask import Response as _Response
from werkzeug.datastructures import ResponseCacheControl
from werkzeug.http import parse_cache_control_header


class Response(_Response):

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
            elif surrogate_control:  # pragma: no cover
                self.headers["Surrogate-Control"] = \
                    surrogate_control.to_header()
        return parse_cache_control_header(
            self.headers.get("surrogate-control"),
            on_update,
            ResponseCacheControl,
        )
