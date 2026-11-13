# SPDX-License-Identifier: Apache-2.0

import gzip
import sys

import pytest

from pyramid.httpexceptions import HTTPServiceUnavailable
from pyramid.request import Request
from pyramid.response import Response

from warehouse.api.problems import PROBLEM_CONTENT_TYPE
from warehouse.api.simple_errors import SimpleAPIErrors


def test_preserves_encoded_problem():
    body = gzip.compress(b'{"status":503,"retry_in":60}')
    app = Response(body, status=503, content_type=PROBLEM_CONTENT_TYPE)
    app.headers.update({"Content-Encoding": "gzip", "Surrogate-Control": "max-age=60"})

    resp = Request.blank("/simple/").get_response(SimpleAPIErrors(app))

    assert resp.body == body
    assert resp.content_encoding == "gzip"
    assert resp.headers["Cache-Control"] == "no-store"
    assert "Surrogate-Control" not in resp.headers


def test_discards_error_representation(mocker):
    stream = mocker.MagicMock()
    app = Response(status="499 Custom Error", app_iter=stream)
    app.headers.update(
        {"ETag": '"original"', "Expires": "0", "Content-Encoding": "gzip"}
    )
    app.headers.add("WWW-Authenticate", 'Basic realm="index"')
    app.headers.add("WWW-Authenticate", "Bearer")

    resp = Request.blank("/simple").get_response(SimpleAPIErrors(app))

    assert resp.status == "499 Custom Error"
    assert resp.json == {"status": 499}
    assert resp.headers.getall("WWW-Authenticate") == ['Basic realm="index"', "Bearer"]
    assert not {"Content-Encoding", "ETag", "Expires"}.intersection(resp.headers)
    stream.__iter__.assert_not_called()
    stream.close.assert_called_once_with()


def test_streams_success_and_closes_on_disconnect(mocker):
    closed = mocker.stub()

    def app(environ, start_response):
        try:
            start_response("200 OK", [])
            yield b"first"
            pytest.fail("Read past the first chunk")
        finally:
            closed()

    start_response = mocker.stub()
    stream = SimpleAPIErrors(app)(Request.blank("/simple/").environ, start_response)
    assert next(stream) == b"first"
    start_response.assert_called_once_with("200 OK", [])
    stream.close()
    closed.assert_called_once_with()


def test_deferred_error():
    def app(environ, start_response):
        yield b""
        start_response("404 Not Found", [])
        yield b"discarded"

    resp = Request.blank("/simple/").get_response(SimpleAPIErrors(app))
    assert resp.json["status"] == 404


def test_failure_before_first_byte():
    def app(environ, start_response):
        start_response("200 OK", [])
        raise HTTPServiceUnavailable("Try later", headers={"Retry-After": "60"})

    resp = Request.blank("/simple/").get_response(SimpleAPIErrors(app))
    assert resp.status_code == 503
    assert resp.json["detail"] == "Try later"
    assert resp.headers["Retry-After"] == "60"


def test_failure_after_first_byte(mocker):
    def app(environ, start_response):
        start_response("200 OK", [])
        yield b"first"
        raise RuntimeError("stream interrupted")

    start_response = mocker.stub()
    body = SimpleAPIErrors(app)(Request.blank("/simple/").environ, start_response)
    assert next(body) == b"first"
    with pytest.raises(RuntimeError, match="stream interrupted"):
        next(body)
    start_response.assert_called_once_with("200 OK", [])


def test_wsgi_error_after_write(mocker):
    error = RuntimeError("already sent")
    start_response = mocker.Mock(side_effect=[mocker.stub(), error])

    def app(environ, start_response):
        write = start_response("200 OK", [])
        write(b"first")
        try:
            raise error
        except RuntimeError:
            start_response("500 Internal Server Error", [], sys.exc_info())

    body = SimpleAPIErrors(app)(Request.blank("/simple/").environ, start_response)
    with pytest.raises(RuntimeError, match="already sent"):
        list(body)
    assert start_response.call_args.args[2][1] is error


@pytest.mark.parametrize("status", ["200 OK", "400 Bad Request"])
def test_wsgi_write_callable(status):
    def app(environ, start_response):
        write = start_response(status, [])
        write(b"first")
        return [b"second"]

    resp = Request.blank("/simple/").get_response(SimpleAPIErrors(app))
    if status == "200 OK":
        assert resp.body == b"firstsecond"
    else:
        assert resp.json["status"] == 400
