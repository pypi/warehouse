# SPDX-License-Identifier: Apache-2.0

import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest

from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.admin.views import ip_addresses as ip_views


class TestIpAddressList:
    def test_no_query(self, db_request):
        ip_addresses = sorted(
            IpAddressFactory.create_batch(30) + [db_request.ip_address]
        )
        db_request.db.add_all(ip_addresses)

        result = ip_views.ip_address_list(db_request)

        assert result["ip_addresses"].items == ip_addresses[:25]
        assert result["q"] is None

    def test_with_page(self, db_request):
        ip_addresses = sorted(
            IpAddressFactory.create_batch(30) + [db_request.ip_address]
        )
        db_request.db.add_all(ip_addresses)

        db_request.GET["page"] = "2"

        result = ip_views.ip_address_list(db_request)

        assert result["ip_addresses"].items == ip_addresses[25:]
        assert result["q"] is None

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_list(request)


class TestIpAddressDetail:
    def test_no_ip_address(self, db_request):
        db_request.matchdict["ip_address_id"] = None

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_ip_address_not_found(self, db_request):
        db_request.matchdict["ip_address_id"] = uuid.uuid4()

        with pytest.raises(HTTPBadRequest):
            ip_views.ip_address_detail(db_request)

    def test_ip_address_found(self, db_request):
        ip_address = IpAddressFactory()
        db_request.matchdict["ip_address_id"] = ip_address.id

        result = ip_views.ip_address_detail(db_request)

        assert result == {"ip_address": ip_address}
