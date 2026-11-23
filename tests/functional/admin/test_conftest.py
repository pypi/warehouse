# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.ip_addresses import IpAddressFactory


class TestLoginFixture:
    def test_reuses_an_existing_ip_row(self, webtest, login_admin):
        """
        `IpAddress.ip_address` is unique and every request upserts the row for
        REMOTE_ADDR, so a test that has already made a request, or made the row
        itself, would otherwise collide with the one the login inserts.
        """
        IpAddressFactory.create(ip_address=REMOTE_ADDR)

        admin = login_admin()

        page = webtest.get(f"/admin/users/{admin.username}/", status=HTTPStatus.OK)
        assert admin.username in page.text
