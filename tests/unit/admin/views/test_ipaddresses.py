# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther

from tests.common.db.accounts import UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.admin.views import ip_addresses as ip_views
from warehouse.ip_addresses.models import BanReason, IpAddress
from warehouse.rate_limiting.interfaces import IRateLimiter


class TestIpAddressList:
    def test_no_query(self, db_request):
        IpAddressFactory.create_batch(30)

        result = ip_views.ip_address_list(db_request)

        assert (
            result["ip_addresses"].items
            == sorted(db_request.db.query(IpAddress).all())[:25]
        )
        assert result["q"] is None

    def test_with_page(self, db_request):
        IpAddressFactory.create_batch(30)
        db_request.GET["page"] = "2"

        result = ip_views.ip_address_list(db_request)

        assert (
            result["ip_addresses"].items
            == sorted(db_request.db.query(IpAddress).all())[25:]
        )
        assert result["q"] is None

    def test_with_invalid_page(self, pyramid_request):
        pyramid_request.params = {"page": "not an integer"}

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_list(pyramid_request)


class TestIpAddressDetail:
    def test_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_invalid_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = "not-an-ip"

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_ip_address_without_record(self, db_request, notfound_ratelimit_service):
        """The 404 limit is keyed on the address, so it shows without a row."""
        db_request.matchdict["ip_address"] = "2001:DB8::1"

        result = ip_views.ip_address_detail(db_request)

        assert result == {
            "ip": "2001:db8::1",
            "ip_address": None,
            "unique_logins": [],
            "notfound_ratelimits": (
                notfound_ratelimit_service.get_window_stats.return_value
            ),
        }
        notfound_ratelimit_service.get_window_stats.assert_called_once_with(
            "2001:db8::1"
        )

    def test_ip_address_found_no_unique_logins(
        self, db_request, notfound_ratelimit_service
    ):
        ip_address = IpAddressFactory()
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)

        result = ip_views.ip_address_detail(db_request)

        assert result == {
            "ip": str(ip_address.ip_address),
            "ip_address": ip_address,
            "unique_logins": [],
            "notfound_ratelimits": (
                notfound_ratelimit_service.get_window_stats.return_value
            ),
        }

    def test_ip_address_found_with_unique_logins(
        self, db_request, notfound_ratelimit_service
    ):
        unique_login = UserUniqueLoginFactory.create(
            ip_address=db_request.ip_address,
        )
        db_request.matchdict["ip_address"] = str(db_request.ip_address.ip_address)

        result = ip_views.ip_address_detail(db_request)

        assert result == {
            "ip": str(db_request.ip_address.ip_address),
            "ip_address": db_request.ip_address,
            "unique_logins": [unique_login],
            "notfound_ratelimits": (
                notfound_ratelimit_service.get_window_stats.return_value
            ),
        }

    def test_ip_address_found_ratelimit_unavailable(
        self, db_request, pyramid_services, ratelimit_service
    ):
        ip_address = IpAddressFactory()
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        # DummyRateLimiter.get_window_stats returns [] (the Redis-down shape).
        pyramid_services.register_service(
            ratelimit_service, IRateLimiter, None, name="notfound.ip"
        )

        result = ip_views.ip_address_detail(db_request)

        assert result["notfound_ratelimits"] == []


class TestBanIpAddress:
    def test_ban_ip_address_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.ban_ip(db_request)

    def test_ban_ip_address_not_found(self, db_request):
        db_request.matchdict["ip_address"] = "69.69.69.69"

        with pytest.raises(HTTPBadRequest):
            ip_views.ban_ip(db_request)

    def test_ban_ip_address_already_banned(self, db_request, mocker):
        ip_address = IpAddressFactory.create(
            is_banned=True,
            ban_reason=BanReason.ADMINISTRATIVE,
            ban_date=datetime.now(UTC),
        )
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = lambda *args, **kwargs: (
            f"/admin/ip-addresses/{ip_address.ip_address}"
        )
        mocker.spy(db_request.session, "flash")

        resp = ip_views.ban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert ip_address.is_banned
        assert ip_address.ban_reason == BanReason.ADMINISTRATIVE
        assert ip_address.ban_date is not None
        db_request.session.flash.assert_called_once_with(
            f"IP address {ip_address.ip_address} is already banned.", queue="warning"
        )

    def test_ban_ip_address_banned(self, db_request, mocker):
        ip_address = IpAddressFactory.create(is_banned=False)
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = lambda *args, **kwargs: (
            f"/admin/ip-addresses/{ip_address.ip_address}"
        )
        mocker.spy(db_request.session, "flash")

        resp = ip_views.ban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert ip_address.is_banned
        assert ip_address.ban_reason == BanReason.ADMINISTRATIVE
        assert ip_address.ban_date is not None


class TestUnbanIpAddress:
    def test_unban_ip_address_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.unban_ip(db_request)

    def test_unban_ip_address_not_found(self, db_request):
        db_request.matchdict["ip_address"] = "69.69.69.69"

        with pytest.raises(HTTPBadRequest):
            ip_views.unban_ip(db_request)

    def test_unban_ip_address_already_unbanned(self, db_request, mocker):
        ip_address = IpAddressFactory.create(is_banned=False)
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = lambda *args, **kwargs: (
            f"/admin/ip-addresses/{ip_address.ip_address}"
        )
        mocker.spy(db_request.session, "flash")

        resp = ip_views.unban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert not ip_address.is_banned
        assert ip_address.ban_reason is None
        assert ip_address.ban_date is None
        db_request.session.flash.assert_called_once_with(
            f"IP address {ip_address.ip_address} is not banned.", queue="warning"
        )

    def test_unban_ip_address_unbanned(self, db_request, mocker):
        ip_address = IpAddressFactory.create(
            is_banned=True,
            ban_reason=BanReason.ADMINISTRATIVE,
            ban_date=datetime.now(UTC),
        )
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = lambda *args, **kwargs: (
            f"/admin/ip-addresses/{ip_address.ip_address}"
        )
        mocker.spy(db_request.session, "flash")

        resp = ip_views.unban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert not ip_address.is_banned
        assert ip_address.ban_reason is None
        assert ip_address.ban_date is None


class TestResetNotfoundRateLimit:
    def test_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.reset_notfound_ratelimit(db_request)

    def test_reset(self, db_request, notfound_ratelimit_service, mocker):
        """Reset needs no IpAddress row, and keys on the canonical address."""
        db_request.matchdict["ip_address"] = "2001:DB8::1"
        mocker.patch.object(
            db_request, "route_path", return_value="/admin/ip-addresses/2001:db8::1/"
        )
        mocker.spy(db_request.session, "flash")

        resp = ip_views.reset_notfound_ratelimit(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == "/admin/ip-addresses/2001:db8::1/"
        db_request.route_path.assert_called_once_with(
            "admin.ip_address.detail", ip_address="2001:db8::1"
        )
        notfound_ratelimit_service.clear.assert_called_once_with("2001:db8::1")
        db_request.session.flash.assert_called_once_with(
            "Reset 404 rate limit for IP address 2001:db8::1", queue="success"
        )
