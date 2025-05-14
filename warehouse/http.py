# SPDX-License-Identifier: Apache-2.0

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
