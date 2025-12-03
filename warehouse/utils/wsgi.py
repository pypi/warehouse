# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import hmac

from typing import TYPE_CHECKING

import sentry_sdk

from sqlalchemy import type_coerce
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import NoResultFound

from warehouse.ip_addresses.models import IpAddress

if TYPE_CHECKING:
    from pyramid.request import Request


GEOIP_FIELDS = {
    "continent_code": "CONTINENT_CODE",
    "country_code": "COUNTRY_CODE",
    "country_code3": "COUNTRY_CODE3",
    "country_name": "COUNTRY_NAME",
    "region": "REGION",
    "city": "CITY",
    "latitude": "LATITUDE",
    "longitude": "LONGITUDE",
}


def _forwarded_value(values, num_proxies):
    values = [v.strip() for v in values.split(",")]
    if len(values) >= num_proxies:
        return values[-num_proxies]


class ProxyFixer:
    def __init__(self, app, token, ip_salt: str, num_proxies=1):
        self.app = app
        self.token = token
        self.ip_salt = ip_salt
        self.num_proxies = num_proxies

    def __call__(self, environ, start_response):
        # Determine if the request comes from a trusted proxy or not by looking
        # for a token in the request.
        request_token = environ.get("HTTP_WAREHOUSE_TOKEN")
        if request_token is not None and hmac.compare_digest(self.token, request_token):
            # Compute our values from the environment.
            proto = environ.get("HTTP_WAREHOUSE_PROTO", "")
            remote_addr = environ.get("HTTP_WAREHOUSE_IP", "")
            remote_addr_hashed = environ.get("HTTP_WAREHOUSE_HASHED_IP", "")

            geoip_info = {
                k: environ.get(f"HTTP_WAREHOUSE_{v}")
                for k, v in GEOIP_FIELDS.items()
                if environ.get(f"HTTP_WAREHOUSE_{v}") is not None
            }

            host = environ.get("HTTP_WAREHOUSE_HOST", "")

        # If we're not getting headers from a trusted third party via the
        # specialized Warehouse-* headers, then we'll fall back to looking at
        # X-Forwarded-* headers, assuming that whatever we have in front of us
        # will strip invalid ones.
        else:
            # If there IS a token, but it doesn't match, then tell us about it.
            if request_token is not None and not hmac.compare_digest(
                self.token, request_token
            ):
                sentry_sdk.set_context(
                    self.__class__.__name__, {"token": request_token}
                )
                sentry_sdk.capture_message(
                    "Invalid Proxy Token",
                    level="warning",
                )

            proto = environ.get("HTTP_X_FORWARDED_PROTO", "")

            # Special case: if we don't see a X-Forwarded-For, this may be a local
            # development instance of Warehouse and the original REMOTE_ADDR is accurate
            remote_addr = _forwarded_value(
                environ.get("HTTP_X_FORWARDED_FOR", ""), self.num_proxies
            ) or environ.get("REMOTE_ADDR")
            remote_addr_hashed = (
                hashlib.sha256((remote_addr + self.ip_salt).encode("utf8")).hexdigest()
                if remote_addr
                else ""
            )
            host = environ.get("HTTP_X_FORWARDED_HOST", "")
            geoip_info = {}

        # Put the new header values into our environment.
        if remote_addr:
            environ["REMOTE_ADDR"] = remote_addr
        if remote_addr_hashed:
            environ["REMOTE_ADDR_HASHED"] = remote_addr_hashed

        for k, v in GEOIP_FIELDS.items():
            if k in geoip_info:
                environ[f"GEOIP_{v}"] = geoip_info[k]

        if host:
            environ["HTTP_HOST"] = host
        if proto:
            environ["wsgi.url_scheme"] = proto

        # Remove any of the forwarded or warehouse headers from the environment
        for header in {
            "HTTP_X_FORWARDED_PROTO",
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_FORWARDED_HOST",
            "HTTP_X_FORWARDED_PORT",
            "HTTP_WAREHOUSE_TOKEN",
            "HTTP_WAREHOUSE_PROTO",
            "HTTP_WAREHOUSE_IP",
            "HTTP_WAREHOUSE_HASHED_IP",
            "HTTP_WAREHOUSE_HOST",
            *[f"HTTP_WAREHOUSE_{v}" for v in GEOIP_FIELDS.values()],
        }:
            if header in environ:
                del environ[header]

        # Dispatch to the real underlying application.
        return self.app(environ, start_response)


class VhmRootRemover:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Delete the X-Vhm-Root header if it exists.
        if "HTTP_X_VHM_ROOT" in environ:
            del environ["HTTP_X_VHM_ROOT"]

        return self.app(environ, start_response)


def _remote_addr_hashed(request: Request) -> str:
    """Return the hashed remote address from the environment."""
    return request.environ.get("REMOTE_ADDR_HASHED", "")


def _ip_address(request):
    """Return the IpAddress object for the remote address from the environment."""
    remote_inet = type_coerce(request.remote_addr, INET)
    try:
        ip_address = request.db.query(IpAddress).filter_by(ip_address=remote_inet).one()
    except NoResultFound:
        ip_address = IpAddress(ip_address=request.remote_addr)
        request.db.add(ip_address)
        request.db.flush()  # To get the id if newly added

    ip_address.hashed_ip_address = request.remote_addr_hashed
    ip_address.geoip_info = {
        k: request.environ[f"GEOIP_{v}"]
        for k, v in GEOIP_FIELDS.items()
        if f"GEOIP_{v}" in request.environ
    }

    return ip_address


def includeme(config):
    # Add property to Request to get the hashed IP address
    config.add_request_method(
        _remote_addr_hashed, name="remote_addr_hashed", property=True, reify=True
    )
    config.add_request_method(_ip_address, name="ip_address", property=True, reify=True)
