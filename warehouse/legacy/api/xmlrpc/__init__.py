# SPDX-License-Identifier: Apache-2.0

from xmlrpc.client import Fault

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPRequestEntityTooLarge,
    HTTPTooManyRequests,
)
from pyramid.interfaces import IRoutesMapper
from pyramid.request import Request
from pyramid.urldispatch import RoutesMapper
from pyramid_rpc.xmlrpc import EndpointPredicate

from warehouse.metrics import IMetricsService
from warehouse.rate_limiting import IRateLimiter
from warehouse.rate_limiting.headers import record_rate_limit

XMLRPC_CONTENT_TYPE = "text/xml"
# The active methods take at most a project name, a username, or a serial.
MAX_XMLRPC_BODY = 8 * 1024


def _check_body_size(request):
    length = request.content_length
    if length is not None:
        if length < 0:
            return HTTPBadRequest()
        if length > MAX_XMLRPC_BODY:
            return HTTPRequestEntityTooLarge()
    elif request.is_body_readable:
        # Chunked input has no Content-Length. Bound the read before
        # pyramid_retry makes its own seekable copy of the body.
        body = bytearray()
        stream = request.body_file
        while chunk := stream.read(MAX_XMLRPC_BODY + 1 - len(body)):
            body.extend(chunk)
            if len(body) > MAX_XMLRPC_BODY:
                return HTTPRequestEntityTooLarge()
        request.body = bytes(body)
    return None


def limit_xmlrpc_body(app, registry):
    mapper = registry.getUtility(IRoutesMapper)
    endpoints = registry.xmlrpc_endpoints
    paths = {mapper.get_route(name).pattern for name in endpoints}
    # /pypi also has :action routes. Preserve their priority without invoking
    # the XML-RPC endpoint predicate, which would read and parse the body.
    routes = RoutesMapper()
    for route in mapper.get_routes():
        if route.pattern in paths:
            predicates = [
                p for p in route.predicates if not isinstance(p, EndpointPredicate)
            ]
            routes.connect(route.name, route.pattern, predicates=predicates)

    def middleware(environ, start_response):
        if environ.get("CONTENT_TYPE", "").startswith(XMLRPC_CONTENT_TYPE):
            request = Request(environ)
            length = request.content_length
            if length is not None and 0 <= length <= MAX_XMLRPC_BODY:
                return app(environ, start_response)
            try:
                route = routes(request)["route"]
            except UnicodeDecodeError:
                return HTTPBadRequest()(environ, start_response)
            if route is not None and route.name in endpoints:
                error = _check_body_size(request)
                if error is not None:
                    return error(environ, start_response)
        return app(environ, start_response)

    return middleware


class XMLRPCWrappedError(Fault):
    def __init__(self, exc):
        self.faultCode = -32500
        self.wrapped_exception = exc

    @property
    def faultString(self):  # noqa: N802
        return f"{self.wrapped_exception.__class__.__name__}: {self.wrapped_exception}"


def check_rate_limit(request):
    limiter = request.find_service(IRateLimiter, name="xmlrpc.client", context=None)
    ip = request.remote_addr
    # pyramid_retry reuses the WSGI environ across attempts.
    charged = request.environ.get("warehouse.xmlrpc.charged")
    allowed = charged or limiter.hit(ip)
    record_rate_limit(
        request, "xmlrpc.client", limiter, identifiers=(ip,), partition_key="ip"
    )
    if charged:
        return

    metrics = request.find_service(IMetricsService, context=None)
    if not allowed:
        metrics.increment("warehouse.xmlrpc.ratelimiter.exceeded", tags=[])
        message = (
            "The action could not be performed because there were too "
            "many requests by the client."
        )
        resets_in = limiter.resets_in(ip)
        if resets_in is not None:
            seconds = max(1, int(resets_in.total_seconds()))
            message += f" Limit may reset in {seconds} seconds."
        raise XMLRPCWrappedError(HTTPTooManyRequests(message))
    request.environ["warehouse.xmlrpc.charged"] = True
    metrics.increment("warehouse.xmlrpc.ratelimiter.hit", tags=[])


class RateLimitedEndpointPredicate(EndpointPredicate):
    def __call__(self, info, request):
        if self.val:
            check_rate_limit(request)
        return super().__call__(info, request)


def includeme(config):
    config.include("pyramid_rpc.xmlrpc")
    config.add_route_predicate(
        "xmlrpc_endpoint",
        RateLimitedEndpointPredicate,
        weighs_more_than=("header", "domain"),
    )
    config.add_wsgi_middleware(limit_xmlrpc_body, config.registry)
    ratelimit_string = config.registry.settings.get(
        "warehouse.xmlrpc.client.ratelimit_string"
    )
    config.register_rate_limiter(ratelimit_string, "xmlrpc.client")
