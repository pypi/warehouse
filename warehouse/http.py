import threading
import requests


class ThreadLocalSessionFactory(threading.local):
    def __init__(self, config=None):
        self.config = config

    def __call__(self, request):
        try:
            return self.session
        except AttributeError:
            self.session = requests.Session()

            if self.config is not None:
                for attr, val in self.config.items():
                    assert hasattr(self.session, attr)
                    setattr(self.session, attr, val)

            return self.session


def includeme(config):
    config.add_request_method(
        ThreadLocalSessionFactory(config.registry.settings.get("http")),
        name="http", reify=True
    )
