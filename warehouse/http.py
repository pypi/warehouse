import threading
import requests


_local = threading.local()


class ThreadLocalSessionFactory:
    def __init__(self, config=None):
        self.config = config

    def __call__(self, request):
        try:
            session = _local.session
            request.log.debug("reusing existing session")
            return session
        except AttributeError:
            request.log.debug("creating new session")
            session = requests.Session()

            if self.config is not None:
                for attr, val in self.config.items():
                    assert hasattr(session, attr)
                    setattr(session, attr, val)

            _local.session = session
            return session


def includeme(config):
    config.add_request_method(
        ThreadLocalSessionFactory(config.registry.settings.get("http")),
        name="http", reify=True
    )
