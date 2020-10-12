import threading

from wsgiref import simple_server

import mechanicalsoup
import pytest

from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session(app_config):
    """
    In the behaviour tests, we need to commit the db for real, otherwise changes
    won't be seen on our servers on the other thread.
    """
    engine = app_config.registry["sqlalchemy.engine"]
    session = sessionmaker()(bind=engine)

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def browser():
    return mechanicalsoup.StatefulBrowser(raise_on_404=True)


@pytest.fixture
def server_config():
    return {"host": "127.0.0.1", "port": 9898}


@pytest.fixture
def server_url(server_config):
    return "http://{host}:{port}".format(**server_config)


class Server(threading.Thread):
    def __init__(self, **kwargs):
        super().__init__(name="Server")
        self.kwargs = kwargs
        self.server = None

    def run(self):
        with simple_server.make_server(**self.kwargs) as server:
            self.server = server
            server.serve_forever()

    def __enter__(self):
        self.start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()

    def __exit__(self, *args, **kwargs):
        self.stop()


@pytest.fixture(autouse=True)
def server(app_config, server_config):
    with Server(**server_config, app=app_config.make_wsgi_app()):
        yield
