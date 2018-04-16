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

import threading
import requests

from urllib.parse import quote_plus


class ThreadLocalSessionFactory:
    def __init__(self, config=None):
        self.config = config
        self._local = threading.local()

    def __call__(self, request):
        try:
            session = self._local.session
            request.log.debug("reusing existing session")
            return session
        except AttributeError:
            request.log.debug("creating new session")
            session = requests.Session()

            if self.config is not None:
                for attr, val in self.config.items():
                    assert hasattr(session, attr)
                    setattr(session, attr, val)

            self._local.session = session
            return session


def unicode_redirect_tween_factory(handler, request):

    def unicode_redirect_tween(request):
        response = handler(request)
        if hasattr(response, "location") and response.location:
            try:
                response.location.encode('ascii')
            except UnicodeEncodeError:
                response.location = '/'.join(
                    [quote_plus(x) for x in response.location.split('/')])

        return response

    return unicode_redirect_tween


def includeme(config):
    config.add_request_method(
        ThreadLocalSessionFactory(config.registry.settings.get("http")),
        name="http", reify=True
    )
    config.add_tween("warehouse.http.unicode_redirect_tween_factory")
