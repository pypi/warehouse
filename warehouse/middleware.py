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


class PoweredBy(object):

    def __init__(self, app, powered_by):
        self.app = app
        self.powered_by = powered_by

    def __call__(self, environ, start_response):
        def _start_response(status, headers, exc_info=None):
            headers.append(("X-Powered-By", self.powered_by))
            return start_response(status, headers, exc_info)

        return self.app(environ, _start_response)
