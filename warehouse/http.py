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

from requests.adapters import HTTPAdapter


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

            adapter = HTTPAdapter(max_retries=1)

            session = requests.Session()
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            if self.config is not None:
                for attr, val in self.config.items():
                    assert hasattr(session, attr)
                    setattr(session, attr, val)

            self._local.session = session
            return session


def includeme(config):
    config.add_request_method(
        ThreadLocalSessionFactory(config.registry.settings.get("http")),
        name="http",
        reify=True,
    )
