# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther

from tests.common.db.accounts import UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.admin.views import ip_addresses as ip_views
from warehouse.ip_addresses.models import BanReason, IpAddress


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

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_list(request)


class TestIpAddressDetail:
    def test_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_ip_address_not_found(self, db_request):
        db_request.matchdict["ip_address"] = "69.69.69.69"

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_ip_address_found_no_unique_logins(self, db_request):
        ip_address = IpAddressFactory()
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)

        result = ip_views.ip_address_detail(db_request)

        assert result == {"ip_address": ip_address, "unique_logins": []}

    def test_ip_address_found_with_unique_logins(self, db_request):
        unique_login = UserUniqueLoginFactory.create(
            ip_address=db_request.ip_address,
        )
        db_request.matchdict["ip_address"] = str(db_request.ip_address.ip_address)

        result = ip_views.ip_address_detail(db_request)

        assert result == {
            "ip_address": db_request.ip_address,
            "unique_logins": [unique_login],
        }


class TestBanIpAddress:
    def test_ban_ip_address_no_ip_address(self, db_request):
        db_request.matchdict["ip_address"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.ban_ip(db_request)

    def test_ban_ip_address_not_found(self, db_request):
        db_request.matchdict["ip_address"] = "69.69.69.69"

        with pytest.raises(HTTPBadRequest):
            ip_views.ban_ip(db_request)

    def test_ban_ip_address_already_banned(self, db_request):
        ip_address = IpAddressFactory.create(
            is_banned=True,
            ban_reason=BanReason.ADMINISTRATIVE,
            ban_date=datetime.utcnow(),
        )
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = pretend.stub(
            __call__=(
                lambda *args, **kwargs: f"/admin/ip-addresses/{ip_address.ip_address}"
            )
        )
        db_request.session.flash = pretend.call_recorder(lambda *args, **kwargs: None)

        resp = ip_views.ban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert ip_address.is_banned
        assert ip_address.ban_reason == BanReason.ADMINISTRATIVE
        assert ip_address.ban_date is not None
        assert db_request.session.flash.calls == [
            pretend.call(
                f"IP address {ip_address.ip_address} is already banned.",
                queue="warning",
            )
        ]

    def test_ban_ip_address_banned(self, db_request):
        ip_address = IpAddressFactory.create(is_banned=False)
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = pretend.stub(
            __call__=(
                lambda *args, **kwargs: f"/admin/ip-addresses/{ip_address.ip_address}"
            )
        )
        db_request.session.flash = pretend.call_recorder(lambda *args, **kwargs: None)

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

    def test_unban_ip_address_already_unbanned(self, db_request):
        ip_address = IpAddressFactory.create(is_banned=False)
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = pretend.stub(
            __call__=(
                lambda *args, **kwargs: f"/admin/ip-addresses/{ip_address.ip_address}"
            )
        )
        db_request.session.flash = pretend.call_recorder(lambda *args, **kwargs: None)

        resp = ip_views.unban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert not ip_address.is_banned
        assert ip_address.ban_reason is None
        assert ip_address.ban_date is None
        assert db_request.session.flash.calls == [
            pretend.call(
                f"IP address {ip_address.ip_address} is not banned.",
                queue="warning",
            )
        ]

    def test_unban_ip_address_unbanned(self, db_request):
        ip_address = IpAddressFactory.create(
            is_banned=True,
            ban_reason=BanReason.ADMINISTRATIVE,
            ban_date=datetime.utcnow(),
        )
        db_request.matchdict["ip_address"] = str(ip_address.ip_address)
        db_request.route_path = pretend.stub(
            __call__=(
                lambda *args, **kwargs: f"/admin/ip-addresses/{ip_address.ip_address}"
            )
        )
        db_request.session.flash = pretend.call_recorder(lambda *args, **kwargs: None)

        resp = ip_views.unban_ip(db_request)

        assert isinstance(resp, HTTPSeeOther)
        assert resp.location == f"/admin/ip-addresses/{ip_address.ip_address}"
        assert not ip_address.is_banned
        assert ip_address.ban_reason is None
        assert ip_address.ban_date is None
