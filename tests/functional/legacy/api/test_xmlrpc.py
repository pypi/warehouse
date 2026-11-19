# SPDX-License-Identifier: Apache-2.0

import xmlrpc.client

from http import HTTPStatus
from io import BytesIO

import pytest

from limits.storage import MemoryStorage
from pyramid.request import Request
from pyramid_retry import RetryableException
from pyramid_rpc import xmlrpc as pyramid_xmlrpc

from warehouse.legacy.api.xmlrpc import MAX_XMLRPC_BODY
from warehouse.legacy.api.xmlrpc.cache.services import RedisXMLRPCCache
from warehouse.rate_limiting import IRateLimiter, RateLimiter


def test_xmlrpc_raises_fault(webtest):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "list_packages", "one", "two")


def test_xmlrpc_nomethod(webtest):
    with pytest.raises(xmlrpc.client.Fault) as excinfo:
        webtest.xmlrpc("/pypi", "multipassssss")
    assert excinfo.value.faultCode == -32601
    assert excinfo.value.faultString == "server error; requested method not found"


@pytest.mark.parametrize("path", ["/pypi", "/pypi/", "/RPC2"])
def test_xmlrpc_succeeds(webtest, mocker, path):
    hit = mocker.spy(RateLimiter, "hit")
    webtest.xmlrpc(path, "changelog_last_serial")
    hit.assert_called_once()


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/pypi"), ("post", "/pypi/"), ("post", "/RPC2"), ("put", "/RPC2")],
)
def test_rate_limit_precedes_parsing(
    webtest, app_config_dbsession_from_env, monkeypatch, mocker, method, path
):
    config = app_config_dbsession_from_env
    factory = config.find_service_factory(IRateLimiter, name="xmlrpc.client")
    monkeypatch.setattr(factory, "limit", "1 per minute")
    monkeypatch.setitem(config.registry, "ratelimiter.storage", MemoryStorage())

    first = webtest.post("/pypi", b"<broken", content_type="text/xml")
    with pytest.raises(xmlrpc.client.Fault) as exc:
        xmlrpc.client.loads(first.body)
    assert exc.value.faultCode == -32700

    parse = mocker.patch("pyramid_rpc.xmlrpc.setup_request")
    response = getattr(webtest, method)(
        path, b"<broken", content_type="text/xml; charset=utf-8"
    )
    with pytest.raises(xmlrpc.client.Fault, match="HTTPTooManyRequests") as exc:
        xmlrpc.client.loads(response.body)
    assert exc.value.faultCode == -32500
    assert '"xmlrpc.client";r=0;' in response.headers["RateLimit"]
    parse.assert_not_called()


@pytest.mark.parametrize(
    ("body", "code"),
    [(b"<broken", -32700), (xmlrpc.client.dumps((), methodname="unknown"), -32601)],
)
def test_invalid_calls_use_quota(webtest, mocker, body, code):
    hit = mocker.spy(RateLimiter, "hit")
    response = webtest.post("/RPC2", body, content_type="text/xml")
    with pytest.raises(xmlrpc.client.Fault) as exc:
        xmlrpc.client.loads(response.body)
    assert exc.value.faultCode == code
    hit.assert_called_once()


def test_cache_hits_use_quota(webtest, mocker):
    projects = {f"project-{i}": i for i in range(300)}
    fetch = mocker.patch.object(RedisXMLRPCCache, "fetch", return_value=projects)
    hit = mocker.spy(RateLimiter, "hit")
    assert webtest.xmlrpc("/pypi", "list_packages_with_serial") == ((projects,), None)
    fetch.assert_called_once()
    hit.assert_called_once()


def test_retries_use_one_quota_slot(webtest, mocker):
    setup = pyramid_xmlrpc.setup_request

    def retry_once(endpoint, request):
        if request.environ["retry.attempt"] == 0:
            raise RetryableException
        return setup(endpoint, request)

    parse = mocker.patch.object(pyramid_xmlrpc, "setup_request", side_effect=retry_once)
    hit = mocker.spy(RateLimiter, "hit")
    body = xmlrpc.client.dumps((), methodname="changelog_last_serial")
    response = webtest.post("/RPC2", body, content_type="text/xml")
    assert xmlrpc.client.loads(response.body) == ((None,), None)
    assert '"xmlrpc.client"' in response.headers["RateLimit"]
    assert parse.call_count == 2
    hit.assert_called_once()


@pytest.mark.parametrize(
    "path", ["/pypi", "/pypi/", "/RPC2", "/RPC2%0A", "/pypi?:action=unknown"]
)
@pytest.mark.parametrize(
    ("length", "status"),
    [
        (MAX_XMLRPC_BODY + 1, HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        (-1, HTTPStatus.BAD_REQUEST),
    ],
)
def test_invalid_length_rejected_before_read(webtest, mocker, path, length, status):
    request = Request.blank(path, method="POST", content_type="text/xml")
    stream = mocker.Mock()
    request.body_file = stream
    request.content_length = length
    parse = mocker.patch("pyramid_rpc.xmlrpc.setup_request")
    assert request.get_response(webtest.app).status_int == status
    stream.read.assert_not_called()
    parse.assert_not_called()


@pytest.mark.parametrize("extra", [0, 1, 1000])
def test_streamed_request_limit(webtest, extra):
    class ShortReads(BytesIO):
        def read(self, size):
            assert 0 < size <= MAX_XMLRPC_BODY + 1
            return super().read(min(size, 256))

    body = xmlrpc.client.dumps((), methodname="changelog_last_serial").encode()
    stream = ShortReads(body.ljust(MAX_XMLRPC_BODY + extra))
    request = Request.blank(
        "/RPC2",
        environ=webtest.extra_environ.copy(),
        method="POST",
        content_type="text/xml",
    )
    request.body_file = stream
    response = request.get_response(webtest.app)
    if extra:
        assert response.status_int == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert stream.tell() == MAX_XMLRPC_BODY + 1
    else:
        assert response.status_int == HTTPStatus.OK
        assert xmlrpc.client.loads(response.body) == ((None,), None)


def test_input_without_a_length_or_eof_marker_is_not_read(webtest, mocker):
    request = Request.blank(
        "/RPC2",
        environ=webtest.extra_environ.copy(),
        method="POST",
        content_type="text/xml",
    )
    stream = mocker.Mock()
    request.body_file = stream
    request.is_body_readable = False
    response = request.get_response(webtest.app)
    with pytest.raises(xmlrpc.client.Fault) as exc:
        xmlrpc.client.loads(response.body)
    assert exc.value.faultCode == -32700
    stream.read.assert_not_called()


@pytest.mark.parametrize(
    ("path", "body", "content_type"),
    [
        (
            "/pypi",
            {":action": "file_upload", "padding": "x" * MAX_XMLRPC_BODY},
            "application/x-www-form-urlencoded",
        ),
        ("/pypi?%3Aaction=file_upload", b"x" * (MAX_XMLRPC_BODY + 1), "text/xml"),
    ],
    ids=["form", "xml-with-action"],
)
def test_legacy_action_does_not_use_xmlrpc_limits(
    webtest, mocker, path, body, content_type
):
    hit = mocker.spy(RateLimiter, "hit")
    response = webtest.post(
        path, body, content_type=content_type, status=HTTPStatus.GONE
    )
    assert "This API has moved" in response.status
    hit.assert_not_called()


def test_invalid_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; package_name: Missing required argument",
    ):
        webtest.xmlrpc("/pypi", "package_releases")


def test_excess_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; 1: Unexpected positional argument",
    ):
        webtest.xmlrpc("/pypi", "changelog_last_serial", 1)


def test_arguments_with_wrong_type(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; serial: Input should be a valid integer",
    ):
        webtest.xmlrpc("/pypi", "changelog_since_serial", "wrong!")


def test_multiple_garbage_types(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=(
            r"client error; since: Input should be a valid integer; with_ids: "
            r"Input should be a valid boolean"
        ),
    ):
        webtest.xmlrpc("/pypi", "changelog", "wrong!", "also wrong!")
