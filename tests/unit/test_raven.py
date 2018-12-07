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

from unittest import mock

import pretend
import pytest
import raven as real_raven

from pyramid.tweens import EXCVIEW, INGRESS
from raven.middleware import Sentry as SentryMiddleware

from warehouse import raven


def test_invalid_serializer():
    s = raven.InvalidSessionSerializer(pretend.stub())
    assert s.serialize(pretend.stub()) == "<InvalidSession>"


class TestRavenTween:
    def test_with_error(self):
        request = pretend.stub(
            raven=pretend.stub(captureException=pretend.call_recorder(lambda: None))
        )

        class TestException(Exception):
            pass

        @pretend.call_recorder
        def handler(request):
            raise TestException

        tween = raven.raven_tween_factory(handler, pretend.stub())

        with pytest.raises(TestException):
            tween(request)

        assert handler.calls == [pretend.call(request)]
        assert request.raven.captureException.calls == [pretend.call()]

    def test_without_error(self):
        request = pretend.stub(
            raven=pretend.stub(captureException=pretend.call_recorder(lambda: None))
        )
        response = pretend.stub()

        @pretend.call_recorder
        def handler(request):
            return response

        tween = raven.raven_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert request.raven.captureException.calls == []


def test_raven_request_method():
    client = pretend.stub(
        context=pretend.stub(clear=pretend.call_recorder(lambda: None))
    )
    request = pretend.stub(
        add_finished_callback=pretend.call_recorder(lambda cb: None),
        registry={"raven.client": client},
        raven=client,
    )
    assert raven._raven(request) is client
    assert request.add_finished_callback.calls == [pretend.call(mock.ANY)]
    assert client.context.clear.calls == []
    cb = request.add_finished_callback.calls[0].args[0]
    cb(request)
    assert client.context.clear.calls == [pretend.call()]


def test_includeme(monkeypatch):
    class Registry(dict):
        def __init__(self):
            self.settings = {}

    client_obj = pretend.stub()
    client_cls = pretend.call_recorder(lambda **kw: client_obj)
    monkeypatch.setattr(real_raven, "Client", client_cls)

    config = pretend.stub(
        registry=Registry(),
        add_request_method=pretend.call_recorder(lambda *a, **kw: None),
        add_wsgi_middleware=pretend.call_recorder(lambda *a, **kw: None),
        add_tween=pretend.call_recorder(lambda *a, **kw: None),
    )
    config.registry.settings.update(
        {
            "warehouse.commit": "blargh",
            "sentry.dsn": "the dsn",
            "sentry.transport": "the transport",
        }
    )

    raven.includeme(config)

    assert client_cls.calls == [
        pretend.call(
            dsn="the dsn",
            include_paths=["warehouse"],
            release="blargh",
            transport="the transport",
            ignore_exceptions=[
                SystemExit,
                "gunicorn.http.errors.ParseException",
                "gunicorn.http.errors.NoMoreData",
                "gunicorn.http.errors.InvalidRequestLine",
                "gunicorn.http.errors.InvalidRequestMethod",
                "gunicorn.http.errors.InvalidHTTPVersion",
                "gunicorn.http.errors.InvalidHeader",
                "gunicorn.http.errors.InvalidHeaderName",
                "gunicorn.http.errors.InvalidChunkSize",
                "gunicorn.http.errors.ChunkMissingTerminator",
                "gunicorn.http.errors.LimitRequestLine",
                "gunicorn.http.errors.LimitRequestHeaders",
                "gunicorn.http.errors.InvalidProxyLine",
                "gunicorn.http.errors.ForbiddenProxyRequest",
                "gunicorn.http.errors.InvalidSchemeHeaders",
            ],
        )
    ]
    assert config.registry["raven.client"] is client_obj
    assert config.add_request_method.calls == [
        pretend.call(raven._raven, name="raven", reify=True)
    ]
    assert config.add_tween.calls == [
        pretend.call(
            "warehouse.raven.raven_tween_factory",
            over=EXCVIEW,
            under=["pyramid_debugtoolbar.toolbar_tween_factory", INGRESS],
        )
    ]
    assert config.add_wsgi_middleware.calls == [
        pretend.call(SentryMiddleware, client=client_obj)
    ]
