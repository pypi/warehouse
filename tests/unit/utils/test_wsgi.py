# SPDX-License-Identifier: Apache-2.0

import pytest
import sentry_sdk

from sqlalchemy.exc import NoResultFound

from warehouse.ip_addresses.models import IpAddress
from warehouse.utils import wsgi

from ...common.constants import REMOTE_ADDR, REMOTE_ADDR_HASHED, REMOTE_ADDR_SALTED
from ...common.db.ip_addresses import IpAddressFactory as DBIpAddressFactory


class TestProxyFixer:
    def test_skips_headers(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {
            "HTTP_WAREHOUSE_TOKEN": "NOPE",
            "HTTP_WAREHOUSE_PROTO": "http",
            "HTTP_WAREHOUSE_IP": REMOTE_ADDR,
            "HTTP_WAREHOUSE_HOST": "example.com",
        }
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token="1234", ip_salt="pepa")(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with({}, start_response)

    def test_token_mismatch_sends_sentry(self, mocker):
        """In the event someone submits the WAREHOUSE_TOKEN header with an
        incorrect value, we send a Sentry.
        """
        mock_set_context = mocker.patch.object(sentry_sdk, "set_context", autospec=True)
        mock_capture_message = mocker.patch.object(
            sentry_sdk, "capture_message", autospec=True
        )

        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {"HTTP_WAREHOUSE_TOKEN": "NOPE"}
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token="1234", ip_salt="pepa")(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with({}, start_response)
        mock_set_context.assert_called_once_with("ProxyFixer", {"token": "NOPE"})
        mock_capture_message.assert_called_once_with(
            "Invalid Proxy Token", level="warning"
        )

    def test_accepts_warehouse_headers(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {
            "HTTP_WAREHOUSE_TOKEN": "1234",
            "HTTP_WAREHOUSE_PROTO": "http",
            "HTTP_WAREHOUSE_IP": REMOTE_ADDR,
            "HTTP_WAREHOUSE_HASHED_IP": "hashbrowns",
            "HTTP_WAREHOUSE_HOST": "example.com",
            "HTTP_WAREHOUSE_CITY": "Anytown, ST",
        }
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token="1234", ip_salt="pepa")(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with(
            {
                "REMOTE_ADDR": REMOTE_ADDR,
                "REMOTE_ADDR_HASHED": "hashbrowns",
                "HTTP_HOST": "example.com",
                "GEOIP_CITY": "Anytown, ST",
                "wsgi.url_scheme": "http",
            },
            start_response,
        )

    def test_missing_headers(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {"HTTP_WAREHOUSE_TOKEN": "1234"}
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token="1234", ip_salt="pepa")(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with({}, start_response)

    def test_accepts_x_forwarded_headers(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {
            "HTTP_X_FORWARDED_PROTO": "http",
            "HTTP_X_FORWARDED_FOR": REMOTE_ADDR,
            "HTTP_X_FORWARDED_HOST": "example.com",
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token=None, ip_salt="pepa")(environ, start_response)

        assert resp is response
        app.assert_called_once_with(
            {
                "HTTP_SOME_OTHER_HEADER": "woop",
                "REMOTE_ADDR": REMOTE_ADDR,
                "REMOTE_ADDR_HASHED": REMOTE_ADDR_SALTED,
                "HTTP_HOST": "example.com",
                "wsgi.url_scheme": "http",
            },
            start_response,
        )

    def test_skips_x_forwarded_when_not_enough(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {
            "HTTP_X_FORWARDED_FOR": REMOTE_ADDR,
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token=None, ip_salt=None, num_proxies=2)(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with({"HTTP_SOME_OTHER_HEADER": "woop"}, start_response)

    def test_selects_right_x_forwarded_value(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)

        environ = {
            "HTTP_X_FORWARDED_PROTO": "http",
            "HTTP_X_FORWARDED_FOR": "192.0.2.2, 192.0.2.1, 192.0.2.3",
            "HTTP_X_FORWARDED_HOST": "example.com",
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = mocker.sentinel.start_response

        resp = wsgi.ProxyFixer(app, token=None, ip_salt="pepa", num_proxies=2)(
            environ, start_response
        )

        assert resp is response
        app.assert_called_once_with(
            {
                "HTTP_SOME_OTHER_HEADER": "woop",
                "REMOTE_ADDR": REMOTE_ADDR,
                "REMOTE_ADDR_HASHED": REMOTE_ADDR_SALTED,
                "HTTP_HOST": "example.com",
                "wsgi.url_scheme": "http",
            },
            start_response,
        )


class TestVhmRootRemover:
    def test_removes_header(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)
        environ = {"HTTP_X_VHM_ROOT": "/foo/bar"}
        start_response = mocker.sentinel.start_response

        resp = wsgi.VhmRootRemover(app)(environ, start_response)

        assert resp is response
        app.assert_called_once_with({}, start_response)

    def test_passes_through_headers(self, mocker):
        response = mocker.sentinel.response
        app = mocker.Mock(return_value=response)
        environ = {"HTTP_X_FOOBAR": "wat"}
        start_response = mocker.sentinel.start_response

        resp = wsgi.VhmRootRemover(app)(environ, start_response)

        assert resp is response
        app.assert_called_once_with({"HTTP_X_FOOBAR": "wat"}, start_response)


def test_ip_address_exists(db_request):
    """When the IP already exists, upsert returns the existing row."""
    ip_address = DBIpAddressFactory(ip_address="192.0.2.69")
    db_request.remote_addr = "192.0.2.69"
    db_request.remote_addr_hashed = ip_address.hashed_ip_address

    assert wsgi._ip_address(db_request) == ip_address


def test_ip_address_created(db_request):
    """When the IP doesn't exist, upsert creates it with metadata."""
    with pytest.raises(NoResultFound):
        db_request.db.query(IpAddress).filter_by(ip_address="192.0.2.69").one()

    db_request.environ["GEOIP_CITY"] = "Anytown, ST"
    db_request.remote_addr = "192.0.2.69"
    db_request.remote_addr_hashed = "deadbeef"

    ip_address = wsgi._ip_address(db_request)

    assert str(ip_address.ip_address) == "192.0.2.69"
    assert ip_address.hashed_ip_address == "deadbeef"
    assert ip_address.geoip_info == {"city": "Anytown, ST"}


def test_ip_address_concurrent_insert(db_request):
    """The upsert handles a conflicting row that exists in the DB but not in
    the ORM identity map — the same scenario as a concurrent INSERT that
    committed between a hypothetical SELECT (miss) and our INSERT.

    Before the upsert fix, _ip_address used SELECT-then-INSERT which would
    raise UniqueViolation in this race condition.
    """
    ip = "192.0.2.69"
    db_request.remote_addr = ip
    db_request.remote_addr_hashed = "deadbeef"

    # Insert the IP directly via Core SQL, bypassing the ORM identity map.
    # This simulates a row committed by a concurrent request that our
    # session doesn't know about.
    db_request.db.execute(IpAddress.__table__.insert().values(ip_address=ip))

    # The upsert should handle the conflict gracefully — no UniqueViolation
    result = wsgi._ip_address(db_request)

    assert str(result.ip_address) == ip
    assert result.hashed_ip_address == "deadbeef"


def test_ip_address_updates_metadata_on_existing(db_request):
    """When the IP already exists, metadata (hash, geoip) should be updated."""
    existing = DBIpAddressFactory(
        ip_address="192.0.2.69",
        hashed_ip_address="oldhash",
        geoip_info={"city": "OldCity"},
    )
    db_request.remote_addr = "192.0.2.69"
    db_request.remote_addr_hashed = "newhash"
    db_request.environ["GEOIP_CITY"] = "NewCity"

    result = wsgi._ip_address(db_request)

    assert result.id == existing.id
    assert result.hashed_ip_address == "newhash"
    assert result.geoip_info == {"city": "NewCity"}


def test_remote_addr_hashed(pyramid_request):
    pyramid_request.environ["REMOTE_ADDR_HASHED"] = REMOTE_ADDR_HASHED

    assert wsgi._remote_addr_hashed(pyramid_request) == REMOTE_ADDR_HASHED


def test_remote_addr_hashed_missing(pyramid_request):
    pyramid_request.environ = {}

    assert wsgi._remote_addr_hashed(pyramid_request) == ""
