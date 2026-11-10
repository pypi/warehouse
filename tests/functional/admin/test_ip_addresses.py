# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.ip_addresses import IpAddressFactory


class TestIpAddressDetail:
    def test_with_record(self, webtest, login_admin):
        login_admin()
        ip_address = IpAddressFactory.create()

        page = webtest.get(
            f"/admin/ip-addresses/{ip_address.ip_address}", status=HTTPStatus.OK
        )

        assert "Ban this IP address" in page.text
        assert "404 Rate Limit" in page.text

    def test_without_record_and_reset(self, webtest, login_admin):
        """An address with no IpAddress row still shows and resets its 404 limit."""
        login_admin()

        page = webtest.get("/admin/ip-addresses/2001:DB8::1", status=HTTPStatus.OK)

        assert "<code>IpAddress</code> record for 2001:db8::1." in page.text
        assert "Ban this IP address" not in page.text

        (reset_form,) = (
            form
            for form in page.forms.values()
            if form.action.endswith("/reset-notfound-ratelimit")
        )
        response = reset_form.submit(status=HTTPStatus.SEE_OTHER)
        assert response.headers["Location"].endswith("/admin/ip-addresses/2001:db8::1")
